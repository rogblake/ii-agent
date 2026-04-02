from __future__ import annotations

import io
import json
import asyncio
from dataclasses import dataclass
from typing import Callable

from ii_agent.core.config.settings import Settings
from ii_agent.core.storage import BaseStorage
from ii_agent.core.storage.client import storage as default_storage
from ii_agent.settings.llm.persisted_settings import PersistedSettings
from ii_agent.settings.llm.store.settings_store import SettingsStore


async def call_sync_from_async(fn: Callable, *args, **kwargs):
    """
    Shorthand for running a function in the default background thread pool executor
    and awaiting the result. The nature of synchronous code is that the future
    returned by this function is not cancellable
    """
    loop = asyncio.get_event_loop()
    coro = loop.run_in_executor(None, lambda: fn(*args, **kwargs))
    result = await coro
    return result


@dataclass
class FileSettingsStore(SettingsStore):
    file_store: BaseStorage
    path: str = "settings.json"

    async def load(self) -> PersistedSettings | None:
        try:
            binary_data = await call_sync_from_async(self.file_store.read, self.path)
            json_str = binary_data.read().decode("utf-8")
            kwargs = json.loads(json_str)
            settings = PersistedSettings(**kwargs)
            return settings
        except FileNotFoundError:
            return None

    async def store(self, settings: PersistedSettings) -> None:
        json_str = settings.model_dump_json(context={"expose_secrets": True})
        content = io.BytesIO(json_str.encode("utf-8"))
        await call_sync_from_async(self.file_store.write, content, self.path)

    @classmethod
    async def get_instance(
        cls, config: Settings, user_id: str | None
    ) -> FileSettingsStore:
        return FileSettingsStore(default_storage)
