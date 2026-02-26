"""Shared fixtures for source_mapping_sync tests."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from ii_agent.projects.design.schemas import ElementContext, StyleChange


class FakeSandbox:
    """In-memory sandbox for testing source-mapping sync functions."""

    def __init__(
        self,
        files: Optional[Dict[str, str]] = None,
        command_outputs: Optional[Dict[str, str]] = None,
    ) -> None:
        self._files: Dict[str, str] = dict(files or {})
        self._command_outputs: Dict[str, str] = dict(command_outputs or {})
        self.written_files: Dict[str, str] = {}

    async def read_file(self, path: str) -> str:
        if path in self._files:
            return self._files[path]
        raise FileNotFoundError(path)

    async def write_file(self, path: str, content: str) -> None:
        self._files[path] = content
        self.written_files[path] = content

    async def run_command(self, cmd: str) -> str:
        for key, output in self._command_outputs.items():
            if key in cmd:
                return output
        return ""


@pytest.fixture
def fake_sandbox():
    """Factory that returns FakeSandbox instances."""

    def _factory(
        files: Optional[Dict[str, str]] = None,
        command_outputs: Optional[Dict[str, str]] = None,
    ) -> FakeSandbox:
        return FakeSandbox(files=files, command_outputs=command_outputs)

    return _factory


def make_style_change(
    *,
    design_id: str = "test-id",
    type: str = "style",
    property: str = "color",
    value: Optional[Dict[str, Any]] = None,
    timestamp: int = 1000,
    element_context: Optional[ElementContext] = None,
) -> StyleChange:
    return StyleChange(
        designId=design_id,
        type=type,
        property=property,
        value=value or {},
        timestamp=timestamp,
        elementContext=element_context,
    )


def make_element_context(
    *,
    design_id: str = "test-id",
    tag_name: str = "div",
    class_name: Optional[str] = None,
    text_content: Optional[str] = None,
    outer_html: Optional[str] = None,
    inner_html: Optional[str] = None,
    context_text: Optional[str] = None,
    prev_sibling_text: Optional[str] = None,
    next_sibling_text: Optional[str] = None,
    react_source: Optional[Dict[str, Any]] = None,
    xpath: Optional[str] = None,
) -> ElementContext:
    return ElementContext(
        designId=design_id,
        tagName=tag_name,
        className=class_name,
        textContent=text_content,
        outerHTML=outer_html,
        innerHTML=inner_html,
        contextText=context_text,
        prevSiblingText=prev_sibling_text,
        nextSiblingText=next_sibling_text,
        reactSource=react_source,
        xpath=xpath,
    )
