from types import SimpleNamespace

import pytest

from ii_agent.billing.exceptions import StripeConfigError
from ii_agent.billing.stripe_config import StripeConfig
from ii_agent.agent.socket.socketio import SocketIOManager

pytestmark = pytest.mark.smoke


class FakeSio:
    def __init__(self):
        self.sessions = {}

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)


@pytest.mark.asyncio
async def test_realtime_connect_sanity(monkeypatch):
    manager = SocketIOManager(FakeSio())

    monkeypatch.setattr(
        "ii_agent.agent.socket.socketio.jwt_handler.verify_access_token",
        lambda token: {"user_id": "u1"},
    )

    accepted = await manager.connect("sid-1", {}, auth={"token": "ok"})

    assert accepted is True


def test_billing_config_missing_secret_key_raises(settings_factory):
    settings = settings_factory(stripe={"secret_key": None})
    stripe_config = StripeConfig(config=settings)

    with pytest.raises(StripeConfigError):
        stripe_config.ensure_api_key()
