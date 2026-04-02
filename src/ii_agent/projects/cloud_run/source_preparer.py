"""Source preparation functions for Cloud Run deployments.

Handles template detection and Dockerfile/watermark injection into source archives.
"""

from __future__ import annotations

import asyncio
import io
import tarfile

from ii_agent.projects.cloud_run.schemas import TemplateType
from ii_agent.projects.cloud_run.templates import (
    DOCKERFILES,
    WATERMARK_INJECTION,
    get_watermark_component,
)
from ii_agent.core.logger import logger


async def detect_template_type(source_bytes: bytes) -> TemplateType:
    """Detect the template type from source archive.

    Args:
        source_bytes: Tar.gz bytes of the source code

    Returns:
        Detected TemplateType
    """

    def _detect():
        files_found: set[str] = set()

        with tarfile.open(fileobj=io.BytesIO(source_bytes), mode="r:gz") as tar:
            for member in tar.getnames():
                # Normalize path
                normalized = member.lstrip("./")
                files_found.add(normalized)

        # Check for Python + React fullstack (has backend/ and frontend/ dirs)
        has_backend = any(f.startswith("backend/") for f in files_found)
        has_frontend = any(f.startswith("frontend/") for f in files_found)
        has_requirements = "backend/requirements.txt" in files_found

        if has_backend and has_frontend and has_requirements:
            # Check if it's shadcn or tailwind variant
            frontend_package = None
            with tarfile.open(fileobj=io.BytesIO(source_bytes), mode="r:gz") as tar:
                try:
                    pkg_member = tar.getmember("frontend/package.json")
                    pkg_file = tar.extractfile(pkg_member)
                    if pkg_file:
                        frontend_package = pkg_file.read().decode("utf-8")
                except KeyError:
                    pass

            if frontend_package:
                if "components.json" in files_found or "@radix-ui" in frontend_package:
                    return TemplateType.REACT_SHADCN_PYTHON
                else:
                    return TemplateType.REACT_TAILWIND_PYTHON
            return TemplateType.REACT_TAILWIND_PYTHON

        # Check for Next.js
        has_next_config = "next.config.js" in files_found or "next.config.mjs" in files_found
        if has_next_config:
            return TemplateType.NEXTJS_SHADCN

        # Check for Vite React
        has_vite_config = "vite.config.ts" in files_found or "vite.config.js" in files_found
        has_package_json = "package.json" in files_found

        if has_vite_config and has_package_json:
            return TemplateType.REACT_VITE_SHADCN

        return TemplateType.UNKNOWN

    return await asyncio.to_thread(_detect)


async def prepare_source_with_dockerfile(source_bytes: bytes, template_type: TemplateType) -> bytes:
    """Add Dockerfile and II-Agent watermark to source archive.

    Args:
        source_bytes: Original tar.gz bytes
        template_type: Detected template type

    Returns:
        Modified tar.gz bytes with Dockerfile and watermark
    """
    if template_type == TemplateType.UNKNOWN:
        # For unknown templates, don't add Dockerfile - use buildpacks
        return source_bytes

    def _add_dockerfile_and_watermark():
        # Read existing archive
        input_buffer = io.BytesIO(source_bytes)
        output_buffer = io.BytesIO()

        # Get watermark injection config for this template type
        watermark_config = WATERMARK_INJECTION.get(template_type)

        with tarfile.open(fileobj=input_buffer, mode="r:gz") as input_tar:
            with tarfile.open(fileobj=output_buffer, mode="w:gz") as output_tar:
                # Check if Dockerfile already exists
                has_dockerfile = any(
                    m.name.lstrip("./") == "Dockerfile" for m in input_tar.getmembers()
                )

                # Track entry file for watermark injection
                entry_file_content = None
                entry_file_member = None

                # Copy all existing files (and capture entry file for modification)
                for member in input_tar.getmembers():
                    normalized_name = member.name.lstrip("./")

                    if member.isfile():
                        file_obj = input_tar.extractfile(member)
                        if file_obj:
                            # Check if this is the entry file we need to modify
                            if (
                                watermark_config
                                and normalized_name == watermark_config["entry_file"]
                            ):
                                # Only buffer the entry file for modification
                                entry_file_content = file_obj.read().decode("utf-8")
                                entry_file_member = member
                            else:
                                # Stream non-entry files directly (no memory buffering)
                                output_tar.addfile(member, file_obj)
                    else:
                        output_tar.addfile(member)

                # Add Dockerfile if not present
                if not has_dockerfile:
                    dockerfile_content = DOCKERFILES.get(
                        template_type, DOCKERFILES[TemplateType.UNKNOWN]
                    )
                    dockerfile_bytes = dockerfile_content.encode("utf-8")

                    dockerfile_info = tarfile.TarInfo(name="Dockerfile")
                    dockerfile_info.size = len(dockerfile_bytes)
                    output_tar.addfile(dockerfile_info, io.BytesIO(dockerfile_bytes))

                # Inject II-Agent watermark
                if watermark_config and entry_file_content and entry_file_member:
                    search_pattern = watermark_config["search_pattern"]
                    replace_pattern = watermark_config["replace_pattern"]

                    # Try flexible pattern matching for <App /> variations
                    # Handles: <App />, <App/>, <App></App>
                    pattern_found = False
                    if search_pattern in entry_file_content:
                        pattern_found = True
                    elif search_pattern == "<App />":
                        # Try common variations
                        for variant in ["<App/>", "<App></App>"]:
                            if variant in entry_file_content:
                                search_pattern = variant
                                # Adjust replace pattern for the variant
                                replace_pattern = replace_pattern.replace(
                                    "<App />", variant.replace("</App>", "")
                                )
                                if variant == "<App></App>":
                                    replace_pattern = "<><App></App><IIAgentBadge /></>"
                                pattern_found = True
                                break

                    # Only inject if pattern was found (avoids unused import errors)
                    if pattern_found:
                        # Add the watermark component file
                        component_bytes = get_watermark_component(
                            watermark_config["component_path"]
                        ).encode("utf-8")
                        component_info = tarfile.TarInfo(name=watermark_config["component_path"])
                        component_info.size = len(component_bytes)
                        output_tar.addfile(component_info, io.BytesIO(component_bytes))

                        # Add import statement after existing imports
                        import_stmt = watermark_config["import_statement"]
                        lines = entry_file_content.split("\n")
                        last_import_idx = -1
                        for i, line in enumerate(lines):
                            if line.strip().startswith("import ") or line.strip().startswith(
                                "from "
                            ):
                                last_import_idx = i

                        if last_import_idx >= 0:
                            lines.insert(last_import_idx + 1, import_stmt.rstrip())
                            entry_file_content = "\n".join(lines)
                        else:
                            # No imports found, add at the beginning
                            entry_file_content = import_stmt + entry_file_content

                        # Replace pattern to include watermark component
                        entry_file_content = entry_file_content.replace(
                            search_pattern,
                            replace_pattern,
                        )

                        # Add modified entry file
                        modified_bytes = entry_file_content.encode("utf-8")
                        modified_info = tarfile.TarInfo(name=entry_file_member.name)
                        modified_info.size = len(modified_bytes)
                        output_tar.addfile(modified_info, io.BytesIO(modified_bytes))
                    else:
                        # Pattern not found - add entry file unmodified
                        # (don't add import to avoid unused import errors)
                        entry_bytes = entry_file_content.encode("utf-8")
                        entry_info = tarfile.TarInfo(name=entry_file_member.name)
                        entry_info.size = len(entry_bytes)
                        output_tar.addfile(entry_info, io.BytesIO(entry_bytes))
                        logger.warning(
                            f"Watermark injection skipped: pattern '{watermark_config['search_pattern']}' "
                            f"not found in {watermark_config['entry_file']}"
                        )

                    logger.info(
                        f"Injected II-Agent watermark into {watermark_config['entry_file']}"
                    )

        return output_buffer.getvalue()

    return await asyncio.to_thread(_add_dockerfile_and_watermark)
