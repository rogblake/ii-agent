"""PNG export functionality for storybooks."""

from __future__ import annotations

import io
import logging
from typing import Optional, Dict, Any, AsyncGenerator

from ii_agent.content.storybook.schemas import StorybookDetail
from ii_agent.content.storybook.export_utils import (
    KATEX_RENDER_SCRIPT,
    prepare_pages_for_export,
    prepare_single_page_for_export,
)

logger = logging.getLogger(__name__)


class StorybookPNGExporter:
    """Handles PNG export for storybooks."""

    async def download_storybook_page_as_png(
        self,
        storybook: StorybookDetail,
        page_number: int,
    ) -> Optional[bytes]:
        """Download a single storybook page as PNG.

        For separate_page mode, the image and text pages are combined into
        a single page for export.
        """
        from playwright.async_api import async_playwright

        if not storybook or not storybook.pages:
            return None

        export_data = prepare_single_page_for_export(
            storybook.pages, page_number, storybook.aspect_ratio, storybook.resolution
        )
        if not export_data:
            return None

        html_content, width, height = export_data

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                )
                page = await context.new_page()
                try:
                    await page.set_content(
                        html_content,
                        wait_until="networkidle",
                        timeout=60000,
                    )
                    await page.evaluate(KATEX_RENDER_SCRIPT)
                    png_bytes = await page.screenshot(type="png", full_page=False)
                    logger.info(f"Created PNG for page {page_number}")
                    return png_bytes
                finally:
                    await page.close()
            finally:
                await browser.close()

    async def download_storybook_as_png_zip(
        self,
        storybook: StorybookDetail,
    ) -> Optional[bytes]:
        """Download all storybook pages as a ZIP of PNGs.

        For separate_page mode storybooks, image and text pages are combined
        into single pages for export.
        """
        import zipfile
        from playwright.async_api import async_playwright

        if not storybook or not storybook.pages:
            return None

        export_pages = prepare_pages_for_export(
            storybook.pages, storybook.aspect_ratio, storybook.resolution
        )
        if not export_pages:
            return None

        png_files = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for page_num, html_content, page_width, page_height in export_pages:
                    logger.info(f"Converting export page {page_num} to PNG ({page_width}x{page_height})")

                    context = await browser.new_context(
                        viewport={"width": page_width, "height": page_height},
                        device_scale_factor=1,
                    )
                    page = await context.new_page()
                    try:
                        await page.set_content(
                            html_content,
                            wait_until="networkidle",
                            timeout=60000,
                        )
                        await page.evaluate(KATEX_RENDER_SCRIPT)
                        png_bytes = await page.screenshot(type="png", full_page=False)
                        png_files.append(
                            {
                                "filename": f"page-{page_num:03d}.png",
                                "data": png_bytes,
                            }
                        )
                        logger.info(f"Successfully converted export page {page_num}")
                    finally:
                        await page.close()
                        await context.close()
            finally:
                await browser.close()

        if not png_files:
            return None

        logger.info("Creating ZIP file...")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for png_file in png_files:
                zf.writestr(png_file["filename"], png_file["data"])

        output.seek(0)
        logger.info(f"Created storybook ZIP with {len(png_files)} pages")
        return output.read()

    async def download_storybook_as_png_with_progress(
        self,
        storybook: StorybookDetail,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download all storybook pages as a ZIP of PNGs with progress updates.

        For separate_page mode storybooks, image and text pages are combined
        into single pages for export.
        """
        import zipfile
        from playwright.async_api import async_playwright
        import base64

        if not storybook or not storybook.pages:
            yield {"type": "error", "message": "Storybook not found or has no pages"}
            return

        export_pages = prepare_pages_for_export(
            storybook.pages, storybook.aspect_ratio, storybook.resolution
        )
        if not export_pages:
            yield {"type": "error", "message": "No pages to export"}
            return

        png_files = []
        total_pages = len(export_pages)

        yield {
            "type": "progress",
            "message": "Starting PNG generation...",
            "current": 0,
            "total": total_pages,
            "percent": 0,
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for index, (page_num, html_content, page_width, page_height) in enumerate(export_pages, 1):
                    yield {
                        "type": "progress",
                        "message": f"Converting page {page_num}",
                        "current": index,
                        "total": total_pages,
                        "percent": round((index / total_pages) * 90, 1),
                    }

                    context = await browser.new_context(
                        viewport={"width": page_width, "height": page_height},
                        device_scale_factor=1,
                    )
                    page = await context.new_page()
                    try:
                        await page.set_content(
                            html_content,
                            wait_until="networkidle",
                            timeout=60000,
                        )
                        await page.evaluate(KATEX_RENDER_SCRIPT)
                        png_bytes = await page.screenshot(type="png", full_page=False)
                        png_files.append(
                            {
                                "filename": f"page-{page_num:03d}.png",
                                "data": png_bytes,
                            }
                        )
                    finally:
                        await page.close()
                        await context.close()
            finally:
                await browser.close()

        if not png_files:
            yield {"type": "error", "message": "No pages to convert"}
            return

        yield {
            "type": "progress",
            "message": "Creating ZIP file...",
            "current": total_pages,
            "total": total_pages,
            "percent": 95.0,
        }

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            for png_file in png_files:
                zf.writestr(png_file["filename"], png_file["data"])

        output.seek(0)
        zip_bytes = output.read()
        zip_base64 = base64.b64encode(zip_bytes).decode("utf-8")

        storybook_id = storybook.id
        filename = (
            f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}-pages.zip"
        )

        yield {
            "type": "complete",
            "message": f"ZIP created with {len(png_files)} pages",
            "filename": filename,
            "zip_base64": zip_base64,
            "total_pages": len(png_files),
        }
