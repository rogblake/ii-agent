"""Shared export preparation helpers for storybook exports."""

from __future__ import annotations

import logging
from typing import List, Optional

from ii_agent.content.storybook.schemas import StorybookPageInfo

logger = logging.getLogger(__name__)

# KaTeX rendering and font loading JavaScript to inject into Playwright pages
KATEX_RENDER_SCRIPT = """
async () => {
    // Wait for all fonts to load (including Crimson Text from Google Fonts)
    if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
    }

    // Load KaTeX script
    await new Promise((resolve, reject) => {
        if (window.katex) {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js';
        script.crossOrigin = 'anonymous';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });

    // Load auto-render extension
    await new Promise((resolve, reject) => {
        if (window.renderMathInElement) {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js';
        script.crossOrigin = 'anonymous';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });

    // Render math in the document
    if (window.renderMathInElement) {
        window.renderMathInElement(document.body, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false },
                { left: '\\\\[', right: '\\\\]', display: true },
                { left: '\\\\(', right: '\\\\)', display: false }
            ],
            throwOnError: false
        });
    }

    // Wait for fonts to fully render and for any final layout adjustments
    await new Promise(resolve => setTimeout(resolve, 300));
}
"""


def find_page_by_number(
    pages: List[StorybookPageInfo], page_number: int
) -> Optional[StorybookPageInfo]:
    """Find a page by its page number."""
    return next((p for p in pages if p.page_number == page_number), None)


def prepare_pages_for_export(
    pages: List[StorybookPageInfo],
    aspect_ratio: str,
    resolution: str,
) -> List[tuple[int, str, int, int]]:
    """Prepare pages for export, combining separate_page pairs.

    For separate_page mode, this combines image-only pages with their
    corresponding text-only pages into a single combined page with
    doubled width (image left + text right).

    Uses stored html_content directly to preserve frontend edits.

    Returns:
        List of (page_number, html_content, width, height) tuples ready for export
    """
    from ii_agent.content.storybook.html_generator import (
        _calculate_dimensions,
        combine_html_pages_for_export,
    )

    if not pages:
        return []

    base_width, base_height = _calculate_dimensions(aspect_ratio, resolution)

    export_pages: List[tuple[int, str, int, int]] = []
    i = 0
    export_page_num = 1

    while i < len(pages):
        current_page = pages[i]
        current_metadata = current_page.metadata or {}

        is_separate_page_image = current_metadata.get("is_separate_page_image", False)

        if is_separate_page_image and i + 1 < len(pages):
            next_page = pages[i + 1]
            next_metadata = next_page.metadata or {}

            if next_metadata.get("is_text_only_page", False):
                logger.info(
                    f"Combining pages {current_page.page_number} (image) and "
                    f"{next_page.page_number} (text) for export"
                )

                if current_page.html_content and next_page.html_content:
                    combined_html, combined_width, combined_height = combine_html_pages_for_export(
                        image_page_html=current_page.html_content,
                        text_page_html=next_page.html_content,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        page_number=export_page_num,
                    )
                    export_pages.append(
                        (export_page_num, combined_html, combined_width, combined_height)
                    )
                export_page_num += 1
                i += 2
                continue

        if current_page.html_content:
            export_pages.append(
                (export_page_num, current_page.html_content, base_width, base_height)
            )
            export_page_num += 1

        i += 1

    return export_pages


def prepare_single_page_for_export(
    pages: List[StorybookPageInfo],
    page_number: int,
    aspect_ratio: str,
    resolution: str,
) -> Optional[tuple[str, int, int]]:
    """Prepare a single page for export, combining separate_page pairs if needed.

    For separate_page mode, if the requested page is an image page or text page,
    this finds the corresponding pair and combines them.

    Uses stored html_content directly to preserve frontend edits.

    Returns:
        Tuple of (html_content, width, height) or None if page not found
    """
    from ii_agent.content.storybook.html_generator import (
        _calculate_dimensions,
        combine_html_pages_for_export,
    )

    page_info = find_page_by_number(pages, page_number)
    if not page_info:
        return None

    page_metadata = page_info.metadata or {}

    is_separate_page_image = page_metadata.get("is_separate_page_image", False)
    is_text_only_page = page_metadata.get("is_text_only_page", False)

    if is_separate_page_image:
        next_page = find_page_by_number(pages, page_number + 1)
        if next_page:
            next_metadata = next_page.metadata or {}
            if next_metadata.get("is_text_only_page", False):
                logger.info(
                    f"Combining pages {page_number} (image) and {page_number + 1} (text) for single page export"
                )
                if page_info.html_content and next_page.html_content:
                    combined_html, combined_width, combined_height = combine_html_pages_for_export(
                        image_page_html=page_info.html_content,
                        text_page_html=next_page.html_content,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        page_number=page_number,
                    )
                    return (combined_html, combined_width, combined_height)

    elif is_text_only_page:
        prev_page = find_page_by_number(pages, page_number - 1)
        if prev_page:
            prev_metadata = prev_page.metadata or {}
            if prev_metadata.get("is_separate_page_image", False):
                logger.info(
                    f"Combining pages {page_number - 1} (image) and {page_number} (text) for single page export"
                )
                if prev_page.html_content and page_info.html_content:
                    combined_html, combined_width, combined_height = combine_html_pages_for_export(
                        image_page_html=prev_page.html_content,
                        text_page_html=page_info.html_content,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        page_number=page_number - 1,
                    )
                    return (combined_html, combined_width, combined_height)

    if not page_info.html_content:
        return None

    width, height = _calculate_dimensions(aspect_ratio, resolution)
    return (page_info.html_content, width, height)
