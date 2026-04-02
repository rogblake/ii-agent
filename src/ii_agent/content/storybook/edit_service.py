"""Storybook edit service for visual design-mode editing."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.credits.service import CreditService
from ii_agent.content.storybook.billing import (
    DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD,
    build_storybook_scope,
    check_and_deduct_storybook_credits,
)
from ii_agent.content.storybook.models import Storybook
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.schemas import DesignChange, StorybookDetail, VersionInfo
from ii_agent.content.storybook.version_service import StorybookVersionService
from ii_agent.content.storybook.voice_service import (
    _extract_plain_text,
    _generate_voice_audio,
    _get_voice_service,
    _resolve_language_code,
)
from ii_agent.projects.design.utils.constants import (
    DESIGN_MODE_GOOGLE_FONTS,
    DESIGN_MODE_RUNTIME_SCRIPT,
)
from ii_agent.projects.design.utils.html_patch import (
    apply_slide_delete_change_with_status,
    apply_slide_icon_change_with_status,
    apply_slide_move_change_with_status,
    apply_slide_style_change_with_status,
    apply_slide_swap_change_with_status,
    apply_slide_text_change_with_status,
)

logger = logging.getLogger(__name__)

STORYBOOK_INLINE_EDIT_SCRIPT = """
<script data-design-ignore="true" data-storybook-inline-edit="true">
(function() {
    if (window.__STORYBOOK_INLINE_EDIT__) return;
    window.__STORYBOOK_INLINE_EDIT__ = true;
    function reportContentSize() {
        var doc = document.documentElement;
        var body = document.body;
        if (!doc || !body) return;
        var width = Math.max(body.scrollWidth, doc.scrollWidth, body.offsetWidth, doc.offsetWidth);
        var height = Math.max(body.scrollHeight, doc.scrollHeight, body.offsetHeight, doc.offsetHeight);
        window.parent.postMessage({
            type: 'DESIGN_MODE_CONTENT_SIZE',
            payload: { width: width, height: height }
        }, '*');
    }
    window.addEventListener('load', reportContentSize);
    window.addEventListener('resize', reportContentSize);
    setInterval(reportContentSize, 500);
})();
</script>
"""


class StorybookEditService:
    """Service for Storybook edit mode orchestration."""

    def __init__(
        self,
        *,
        repo: StorybookRepository,
        version_service: StorybookVersionService,
        credit_service: CreditService,
    ) -> None:
        self._repo = repo
        self._version_service = version_service
        self._credit_service = credit_service

    async def get_page_html_with_runtime(
        self,
        db: AsyncSession,
        *,
        storybook_id: str,
        page_number: int,
    ) -> Optional[str]:
        """Fetch a storybook page and inject design-mode runtime scripts."""
        page = await self._repo.get_page_by_number(db, storybook_id, page_number)
        if not page or not page.html_content:
            return None
        return self._inject_runtime_script(page.html_content)

    async def apply_changes_to_html(
        self,
        html_content: str,
        changes: List[DesignChange],
    ) -> str:
        """Apply change payloads from Storybook edit mode to HTML."""
        if not html_content or not changes:
            return html_content

        updated_html = html_content

        for change in changes:
            design_id = (change.designId or "").strip()
            if not design_id:
                continue

            change_type = (change.type or "").strip().lower()
            property_name = (change.property or "").strip()
            raw_value = change.value.get("to") if isinstance(change.value, dict) else None
            new_value = "" if raw_value is None else str(raw_value)

            context = change.elementContext if isinstance(change.elementContext, dict) else None
            xpath = self._extract_xpath(context)
            slide_number = self._extract_slide_number(context)

            try:
                if change_type == "style":
                    updated_html, _ = apply_slide_style_change_with_status(
                        updated_html,
                        design_id,
                        property_name,
                        new_value,
                        xpath=xpath,
                        slide_number=slide_number,
                    )
                    continue

                if change_type == "text":
                    updated_html, _ = apply_slide_text_change_with_status(
                        updated_html,
                        design_id,
                        new_value,
                        xpath=xpath,
                        slide_number=slide_number,
                    )
                    continue

                if change_type == "attribute" and property_name == "icon":
                    updated_html, _ = apply_slide_icon_change_with_status(
                        updated_html,
                        design_id,
                        new_value,
                        xpath=xpath,
                        slide_number=slide_number,
                    )
                    continue

                if change_type == "attribute":
                    updated_html, _ = self._apply_attribute_change(
                        updated_html,
                        design_id=design_id,
                        attr=property_name,
                        value=raw_value,
                        context=context,
                    )
                    continue

                if change_type == "delete":
                    updated_html, _ = apply_slide_delete_change_with_status(
                        updated_html,
                        design_id=design_id,
                        file_path=f"storybook_{slide_number or 0}",
                    )
                    continue

                if change_type == "move":
                    updated_html, _ = apply_slide_move_change_with_status(
                        updated_html,
                        design_id=design_id,
                        anchor=new_value,
                        file_path=f"storybook_{slide_number or 0}",
                    )
                    continue

                if change_type == "swap":
                    updated_html, _ = apply_slide_swap_change_with_status(
                        updated_html,
                        design_id=design_id,
                        target_design_id=new_value,
                        file_path=f"storybook_{slide_number or 0}",
                    )
                    continue

                logger.debug(
                    "[StorybookEdit] Unsupported change type=%s property=%s",
                    change_type,
                    property_name,
                )
            except Exception as exc:
                logger.warning(
                    "[StorybookEdit] Failed applying change id=%s type=%s: %s",
                    design_id,
                    change_type,
                    exc,
                )

        return updated_html

    async def save_all_page_edits(
        self,
        db: AsyncSession,
        *,
        storybook_id: str,
        page_changes: Dict[int, List[DesignChange]],
        image_urls: Optional[Dict[int, str]] = None,
    ) -> tuple[Optional[StorybookDetail], float]:
        """Apply edits across pages and create one new storybook version."""
        if not page_changes and not image_urls:
            return None, 0.0

        image_urls = image_urls or {}
        source_storybook = await self._repo.get_by_id(db, storybook_id)
        if not source_storybook:
            return None, 0.0

        source_pages_by_number = {page.page_number: page for page in (source_storybook.pages or [])}
        style_json = (
            source_storybook.style_json if isinstance(source_storybook.style_json, dict) else {}
        )
        language_code = _resolve_language_code(None, style_json)
        voice_enabled = bool(style_json.get("voice_enabled", False))
        session_id = source_storybook.session_id or ""
        voice_service = _get_voice_service() if voice_enabled and session_id else None

        page_updates: Dict[int, Dict[str, Any]] = {}
        total_voice_cost_usd = 0.0

        all_page_numbers = set(page_changes.keys()) | set(image_urls.keys())
        for page_number in sorted(all_page_numbers):
            source_page = source_pages_by_number.get(page_number)
            if not source_page:
                logger.warning(
                    "[StorybookEdit] Missing page_number=%s in storybook=%s",
                    page_number,
                    storybook_id,
                )
                continue

            updates: Dict[str, Any] = {}
            changes = page_changes.get(page_number) or []

            if changes:
                original_html = source_page.html_content or ""
                if original_html:
                    modified_html = await self.apply_changes_to_html(original_html, changes)
                    updates["html_content"] = modified_html
                    new_text = _extract_plain_text(modified_html)
                    updates["text_content"] = new_text

                    has_text_changes = any(
                        (change.type or "").lower() == "text" for change in changes
                    )
                    if has_text_changes and voice_service and session_id:
                        audio_link, voice_cost = await _generate_voice_audio(
                            voice_service,
                            text=new_text,
                            session_id=session_id,
                            language_code=language_code,
                        )
                        if audio_link:
                            updates["audio_link"] = audio_link
                            total_voice_cost_usd += voice_cost
                else:
                    logger.warning(
                        "[StorybookEdit] No html_content for storybook=%s page=%s",
                        storybook_id,
                        page_number,
                    )

            if page_number in image_urls:
                updates["image_url"] = image_urls[page_number]

            if updates:
                page_updates[page_number] = updates

        if not page_updates:
            return None, 0.0

        new_storybook = await self._version_service.create_storybook_version_multi_page(
            db,
            source_storybook_id=storybook_id,
            page_updates=page_updates,
        )
        return new_storybook, total_voice_cost_usd

    async def save_all_page_edits_with_billing(
        self,
        db: AsyncSession,
        *,
        storybook_id: str,
        user_id: str,
        page_changes: Dict[int, List[DesignChange]],
        image_urls: Optional[Dict[int, str]] = None,
    ) -> Optional[StorybookDetail]:
        """Apply storybook edits and deduct any regenerated voice cost."""
        source_storybook = await self._repo.get_by_id(db, storybook_id)
        if source_storybook is None:
            return None

        estimated_voice_pages = self._estimate_voice_pages_for_edits(
            storybook=source_storybook,
            page_changes=page_changes,
        )
        if estimated_voice_pages <= 0:
            new_storybook, _ = await self.save_all_page_edits(
                db,
                storybook_id=storybook_id,
                page_changes=page_changes,
                image_urls=image_urls,
            )
            return new_storybook

        session_id = source_storybook.session_id or ""
        if not session_id:
            new_storybook, _ = await self.save_all_page_edits(
                db,
                storybook_id=storybook_id,
                page_changes=page_changes,
                image_urls=image_urls,
            )
            return new_storybook

        scope = build_storybook_scope(
            user_id=user_id,
            session_id=session_id,
        )

        # 1. Check credits up-front
        estimated_cost = float(DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD * estimated_voice_pages)
        has_credits = await self._credit_service.has_sufficient_credits(db, user_id, estimated_cost)
        if not has_credits:
            raise InsufficientCreditsError(
                available_credits=0.0,
                required_credits=estimated_cost,
            )

        # 2. Execute the operation
        new_storybook, total_voice_cost_usd = await self.save_all_page_edits(
            db,
            storybook_id=storybook_id,
            page_changes=page_changes,
            image_urls=image_urls,
        )

        # 3. Deduct actual cost
        if total_voice_cost_usd > 0:
            await check_and_deduct_storybook_credits(
                db,
                credit_service=self._credit_service,
                scope=scope,
                amount_usd=total_voice_cost_usd,
                tool_name="storybook_edit_voice",
                metadata={
                    "storybook_id": storybook_id,
                    "voice_page_count_estimate": estimated_voice_pages,
                },
            )

        return new_storybook

    @staticmethod
    def _estimate_voice_pages_for_edits(
        *,
        storybook,
        page_changes: Dict[int, List[DesignChange]],
    ) -> int:
        """Estimate billable voice regenerations caused by text edits."""
        style_json = storybook.style_json if isinstance(storybook.style_json, dict) else {}
        if not style_json.get("voice_enabled"):
            return 0

        billable_pages = 0
        source_pages = {page.page_number: page for page in (storybook.pages or [])}
        for page_number, changes in (page_changes or {}).items():
            if not any((change.type or "").lower() == "text" for change in (changes or [])):
                continue

            page = source_pages.get(page_number)
            if page and page.html_content:
                billable_pages += 1

        return billable_pages

    async def get_version_history(
        self,
        db: AsyncSession,
        *,
        storybook_id: str,
    ) -> List[VersionInfo]:
        """Get version history for a storybook family (newest first)."""
        storybook = await self._repo.get_by_id(db, storybook_id)
        if not storybook:
            return []

        root_id = storybook.root_storybook_id or await self._resolve_root_storybook_id(
            db, storybook
        )
        if not root_id:
            return []

        versions = await self._repo.get_version_family(db, root_id)
        return [
            VersionInfo(
                id=version.id,
                version=version.version or 1,
                created_at=version.created_at,
                is_current=(version.id == storybook_id),
            )
            for version in versions
        ]

    @staticmethod
    def _inject_runtime_script(html: str) -> str:
        runtime_present = "__DESIGN_MODE_RUNTIME__" in html
        inline_present = 'data-storybook-inline-edit="true"' in html

        injection_parts: list[str] = []
        if not runtime_present:
            injection_parts.append(DESIGN_MODE_GOOGLE_FONTS)
            injection_parts.append(DESIGN_MODE_RUNTIME_SCRIPT)
        if not inline_present:
            injection_parts.append(STORYBOOK_INLINE_EDIT_SCRIPT)

        injection = "\n".join(part for part in injection_parts if part)
        if not injection:
            return html

        if "<head>" in html:
            return html.replace("<head>", f"<head>\n{injection}\n", 1)
        if "<head " in html:
            return re.sub(
                r"(<head[^>]*>)",
                lambda m: f"{m.group(1)}\n{injection}\n",
                html,
                count=1,
            )
        if "<html>" in html or "<html " in html:
            return re.sub(
                r"(<html[^>]*>)",
                lambda m: f"{m.group(1)}\n<head>\n{injection}\n</head>\n",
                html,
                count=1,
            )
        return f"{injection}\n{html}"

    async def _resolve_root_storybook_id(
        self,
        db: AsyncSession,
        storybook: Storybook,
    ) -> Optional[str]:
        """Walk parent pointers to find the family root when root_id is missing."""
        current = storybook
        visited: set[str] = set()

        while current and current.id not in visited:
            visited.add(current.id)
            if not current.parent_storybook_id:
                return current.id
            current = await self._repo.get_by_id(db, current.parent_storybook_id)
        return None

    @staticmethod
    def _extract_xpath(context: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(context, dict):
            return None
        xpath = context.get("xpath")
        if isinstance(xpath, str) and xpath.strip():
            return xpath.strip()
        return None

    @staticmethod
    def _extract_slide_number(context: Optional[Dict[str, Any]]) -> Optional[int]:
        if not isinstance(context, dict):
            return None
        value = context.get("slideNumber")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _find_element_by_context(
        soup: BeautifulSoup,
        context: Dict[str, Any],
    ) -> Any:
        tag_name = context.get("tagName")
        if not tag_name:
            return None

        candidates = soup.find_all(tag_name)
        if not candidates:
            return None

        element_id = context.get("id")
        if element_id:
            for element in candidates:
                if element.get("id") == element_id:
                    return element

        class_name = context.get("className")
        if class_name:
            class_tokens = [token for token in class_name.split() if token]
            if class_tokens:
                for element in candidates:
                    classes = element.get("class", [])
                    if isinstance(classes, str):
                        classes = classes.split()
                    if all(token in classes for token in class_tokens):
                        return element

        attributes = context.get("attributes") or {}
        if isinstance(attributes, dict) and attributes:
            for element in candidates:
                if all(str(element.get(k, "")) == str(v) for k, v in attributes.items()):
                    return element

        text_content = context.get("textContent")
        if isinstance(text_content, str) and text_content.strip():
            needle = text_content.strip()
            for element in candidates:
                if needle in element.get_text(strip=True):
                    return element

        return candidates[0]

    def _apply_attribute_change(
        self,
        html_content: str,
        *,
        design_id: str,
        attr: str,
        value: Any,
        context: Optional[Dict[str, Any]],
    ) -> tuple[str, bool]:
        if not attr:
            return html_content, False

        soup = BeautifulSoup(html_content, "html.parser")
        element = soup.find(attrs={"data-design-id": design_id})
        if not element and context:
            element = self._find_element_by_context(soup, context)
            if element:
                element["data-design-id"] = design_id

        if not element:
            return html_content, False

        normalized_attr = "class" if attr == "className" else attr
        if value is None or (isinstance(value, str) and not value.strip()):
            element.attrs.pop(normalized_attr, None)
            return str(soup), True

        if normalized_attr == "class":
            element["class"] = str(value).split()
        else:
            element[normalized_attr] = str(value)
        return str(soup), True
