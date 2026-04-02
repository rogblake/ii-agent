from types import SimpleNamespace

import pytest

from ii_agent.realtime.socket.command.command_handler import UserCommandType
from ii_agent.realtime.socket.command.handler_factory import CommandHandlerFactory


@pytest.mark.asyncio
async def test_initialize_runs_once_and_sets_initialized_flag(monkeypatch):
    factory = CommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())

    call_count = {"count": 0}

    async def _fake_init_handlers():
        call_count["count"] += 1
        factory._handlers = {UserCommandType.PING: object()}

    monkeypatch.setattr(factory, "_initialize_handlers", _fake_init_handlers)

    await factory.initialize()
    await factory.initialize()

    assert factory._initialized is True
    assert call_count["count"] == 1


def test_get_handler_by_string_returns_none_for_unknown_type():
    factory = CommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())

    assert factory.get_handler_by_string("does_not_exist") is None


def test_get_handler_by_string_returns_handler_for_known_type():
    handler = object()
    factory = CommandHandlerFactory(sio=SimpleNamespace(), container=SimpleNamespace())
    factory._handlers = {UserCommandType.PING: handler}

    assert factory.get_handler_by_string("ping") is handler
