"""Coverage tests for celery model import bootstrap."""
from __future__ import annotations

from unittest.mock import Mock

from ii_agent.workers.celery import model_imports


def test_import_model_modules_registers_models_once(monkeypatch):
    module_calls = []

    monkeypatch.setattr(model_imports, "configure_mappers", Mock())
    monkeypatch.setattr(
        model_imports,
        "import_module",
        lambda module_path: module_calls.append(module_path),
    )
    model_imports.import_model_modules.cache_clear()

    model_imports.import_model_modules()
    assert module_calls == list(model_imports.MODEL_MODULES)
    model_imports.configure_mappers.assert_called_once()

    first_call_count = len(module_calls)
    model_imports.import_model_modules()
    assert len(module_calls) == first_call_count
