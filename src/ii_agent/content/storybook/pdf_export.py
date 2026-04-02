"""PDF export functionality for storybooks."""

from __future__ import annotations

import io
import logging
from typing import Optional, Dict, Any, AsyncGenerator, TYPE_CHECKING

from PIL import Image

from ii_agent.content.storybook.schemas import StorybookDetail
from ii_agent.content.storybook.export_utils import (
    KATEX_RENDER_SCRIPT,
    prepare_pages_for_export,
    prepare_single_page_for_export,
)

if TYPE_CHECKING:
    from pypdf import PdfWriter

logger = logging.getLogger(__name__)


class StorybookPDFExporter:
    """Handles PDF export for storybooks."""

    async def download_storybook_as_pdf(
        self,
        storybook: StorybookDetail,
    ) -> Optional[bytes]:
        """Download a storybook as PDF.

        For separate_page mode storybooks, image and text pages are combined
        into single pages for export.
        """
        from playwright.async_api import async_playwright
        from pypdf import PdfWriter, PdfReader

        if not storybook or not storybook.pages:
            return None

        export_pages = prepare_pages_for_export(
            storybook.pages, storybook.aspect_ratio, storybook.resolution
        )
        if not export_pages:
            return None

        pdf_buffers = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for page_num, html_content, page_width, page_height in export_pages:
                    logger.info(
                        f"Converting export page {page_num} to PDF ({page_width}x{page_height})"
                    )

                    context = await browser.new_context(
                        viewport={"width": page_width, "height": page_height}
                    )
                    page = await context.new_page()
                    try:
                        await page.wait_for_load_state("domcontentloaded")
                        await page.set_content(
                            html_content,
                            wait_until="networkidle",
                            timeout=60000,
                        )
                        await page.evaluate(KATEX_RENDER_SCRIPT)
                        pdf_buffer = await page.pdf(
                            print_background=True,
                            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                            display_header_footer=False,
                            prefer_css_page_size=False,
                            scale=1,
                            width=f"{page_width}px",
                            height=f"{page_height}px",
                        )
                        pdf_buffers.append(pdf_buffer)
                        logger.info(f"Successfully converted export page {page_num}")
                    finally:
                        await page.close()
                        await context.close()
            finally:
                await browser.close()

        if not pdf_buffers:
            return None

        logger.info("Merging PDFs...")
        pdf_writer = PdfWriter()
        for pdf_buffer in pdf_buffers:
            pdf_reader = PdfReader(io.BytesIO(pdf_buffer))
            for pg in pdf_reader.pages:
                pdf_writer.add_page(pg)

        logger.info("Compressing PDF images...")
        compress_pdf_images(pdf_writer, quality=75, max_dimension=1920)

        logger.info("Compressing PDF content streams...")
        for pg in pdf_writer.pages:
            pg.compress_content_streams()
        pdf_writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)
        logger.info(f"Created storybook PDF with {len(pdf_writer.pages)} pages")
        return output.read()

    async def download_storybook_as_pdf_with_progress(
        self,
        storybook: StorybookDetail,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download a storybook as PDF with progress updates.

        For separate_page mode storybooks, image and text pages are combined
        into single pages for export.
        """
        from playwright.async_api import async_playwright
        from pypdf import PdfWriter, PdfReader
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

        pdf_buffers = []
        total_pages = len(export_pages)

        yield {
            "type": "progress",
            "message": "Starting PDF generation...",
            "current": 0,
            "total": total_pages,
            "percent": 0,
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                for index, (page_num, html_content, page_width, page_height) in enumerate(
                    export_pages, 1
                ):
                    yield {
                        "type": "progress",
                        "message": f"Converting page {page_num}",
                        "current": index,
                        "total": total_pages,
                        "percent": round((index / total_pages) * 90, 1),
                    }

                    context = await browser.new_context(
                        viewport={"width": page_width, "height": page_height}
                    )
                    page = await context.new_page()
                    try:
                        await page.wait_for_load_state("domcontentloaded")
                        await page.set_content(
                            html_content,
                            wait_until="networkidle",
                            timeout=60000,
                        )
                        await page.evaluate(KATEX_RENDER_SCRIPT)
                        pdf_buffer = await page.pdf(
                            print_background=True,
                            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                            display_header_footer=False,
                            prefer_css_page_size=False,
                            scale=1,
                            width=f"{page_width}px",
                            height=f"{page_height}px",
                        )
                        pdf_buffers.append(pdf_buffer)
                    finally:
                        await page.close()
                        await context.close()
            finally:
                await browser.close()

        if not pdf_buffers:
            yield {"type": "error", "message": "No pages to convert"}
            return

        yield {
            "type": "progress",
            "message": "Merging PDFs...",
            "current": total_pages,
            "total": total_pages,
            "percent": 90.0,
        }

        pdf_writer = PdfWriter()
        for pdf_buffer in pdf_buffers:
            pdf_reader = PdfReader(io.BytesIO(pdf_buffer))
            for pg in pdf_reader.pages:
                pdf_writer.add_page(pg)

        yield {
            "type": "progress",
            "message": "Compressing images...",
            "current": total_pages,
            "total": total_pages,
            "percent": 93.0,
        }

        compress_pdf_images(pdf_writer, quality=75, max_dimension=1920)

        yield {
            "type": "progress",
            "message": "Optimizing PDF...",
            "current": total_pages,
            "total": total_pages,
            "percent": 97.0,
        }

        for pg in pdf_writer.pages:
            pg.compress_content_streams()
        pdf_writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)

        pdf_bytes = output.read()
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        storybook_id = storybook.id
        filename = f"{storybook.name.replace(' ', '_')}_{storybook_id[:8]}.pdf"

        yield {
            "type": "complete",
            "message": f"PDF created with {len(pdf_writer.pages)} pages",
            "filename": filename,
            "pdf_base64": pdf_base64,
            "total_pages": len(pdf_writer.pages),
        }

    async def download_storybook_page_as_pdf(
        self,
        storybook: StorybookDetail,
        page_number: int,
    ) -> Optional[bytes]:
        """Download a single storybook page as PDF.

        For separate_page mode, the image and text pages are combined into
        a single page for export.
        """
        from playwright.async_api import async_playwright
        from pypdf import PdfWriter, PdfReader

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
                context = await browser.new_context(viewport={"width": width, "height": height})
                page = await context.new_page()
                try:
                    await page.wait_for_load_state("domcontentloaded")
                    await page.set_content(
                        html_content,
                        wait_until="networkidle",
                        timeout=60000,
                    )
                    await page.evaluate(KATEX_RENDER_SCRIPT)
                    pdf_buffer = await page.pdf(
                        print_background=True,
                        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                        display_header_footer=False,
                        prefer_css_page_size=False,
                        scale=1,
                        width=f"{width}px",
                        height=f"{height}px",
                    )
                finally:
                    await page.close()
            finally:
                await browser.close()

        logger.info(f"Compressing PDF for page {page_number}...")
        pdf_reader = PdfReader(io.BytesIO(pdf_buffer))
        pdf_writer = PdfWriter()
        for pdf_page in pdf_reader.pages:
            pdf_writer.add_page(pdf_page)

        compress_pdf_images(pdf_writer, quality=75, max_dimension=1920)
        for pdf_page in pdf_writer.pages:
            pdf_page.compress_content_streams()
        pdf_writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

        output = io.BytesIO()
        pdf_writer.write(output)
        output.seek(0)
        logger.info(f"Created compressed PDF for page {page_number}")
        return output.read()


def compress_pdf_images(
    pdf_writer: "PdfWriter",
    quality: int = 75,
    max_dimension: int = 1920,
) -> None:
    """Compress images in a PDF to reduce file size."""
    from pypdf.generic import (
        ArrayObject,
        NameObject,
        IndirectObject,
    )

    processed_images: set = set()

    for page in pdf_writer.pages:
        if "/Resources" not in page:
            continue

        resources = page["/Resources"]
        if isinstance(resources, IndirectObject):
            resources = resources.get_object()

        if "/XObject" not in resources:
            continue

        xobject = resources["/XObject"]
        if isinstance(xobject, IndirectObject):
            xobject = xobject.get_object()

        for obj_name in xobject:
            obj = xobject[obj_name]
            if isinstance(obj, IndirectObject):
                obj_id = obj.idnum
                if obj_id in processed_images:
                    continue
                processed_images.add(obj_id)
                obj = obj.get_object()

            if obj.get("/Subtype") != "/Image":
                continue

            try:
                width = int(obj.get("/Width", 0))
                height = int(obj.get("/Height", 0))
                if width == 0 or height == 0:
                    continue

                data = obj.get_data()
                if not data:
                    continue

                color_space = obj.get("/ColorSpace")
                if isinstance(color_space, ArrayObject):
                    color_space = str(color_space[0])
                else:
                    color_space = str(color_space) if color_space else "/DeviceRGB"

                if "/DeviceGray" in color_space or "/CalGray" in color_space:
                    mode = "L"
                elif "/DeviceCMYK" in color_space:
                    mode = "CMYK"
                else:
                    mode = "RGB"

                try:
                    img = Image.open(io.BytesIO(data))
                except Exception:
                    if mode == "L":
                        expected_size = width * height
                    elif mode == "RGB":
                        expected_size = width * height * 3
                    elif mode == "CMYK":
                        expected_size = width * height * 4
                    else:
                        continue

                    if len(data) < expected_size:
                        continue

                    try:
                        img = Image.frombytes(mode, (width, height), data[:expected_size])
                    except Exception:
                        continue

                if max(img.width, img.height) > max_dimension:
                    ratio = max_dimension / max(img.width, img.height)
                    new_width = int(img.width * ratio)
                    new_height = int(img.height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")

                if img.mode == "CMYK":
                    img = img.convert("RGB")
                elif img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")

                output_buffer = io.BytesIO()
                img.save(output_buffer, format="JPEG", quality=quality, optimize=True)
                compressed_data = output_buffer.getvalue()

                if len(compressed_data) < len(data):
                    obj._data = compressed_data
                    obj[NameObject("/Filter")] = NameObject("/DCTDecode")
                    obj[NameObject("/Width")] = width if img.width == width else img.width
                    obj[NameObject("/Height")] = height if img.height == height else img.height
                    obj[NameObject("/BitsPerComponent")] = 8
                    obj[NameObject("/ColorSpace")] = NameObject(
                        "/DeviceGray" if img.mode == "L" else "/DeviceRGB"
                    )
                    if "/DecodeParms" in obj:
                        del obj["/DecodeParms"]
                    logger.debug(
                        f"Compressed image: {len(data)} -> {len(compressed_data)} bytes "
                        f"({100 - len(compressed_data) * 100 // len(data)}% reduction)"
                    )

            except Exception as e:
                logger.debug(f"Could not compress image: {e}")
                continue
