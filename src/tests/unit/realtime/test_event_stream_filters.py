import pytest

from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.realtime.socket.event_stream_filters import SilentEventStream


class FakeInnerStream:
    def __init__(self):
        self.published = []
        self.name = "inner-stream"

    async def publish(self, event):
        self.published.append(event)


@pytest.mark.asyncio
async def test_silent_event_stream_suppresses_agent_response_events():
    inner = FakeInnerStream()
    stream = SilentEventStream(inner)

    event = RealtimeEvent(type=EventType.AGENT_RESPONSE, content={"text": "thinking"})
    await stream.publish(event)

    assert inner.published == []


@pytest.mark.asyncio
async def test_silent_event_stream_forwards_non_agent_response_events():
    inner = FakeInnerStream()
    stream = SilentEventStream(inner)

    event = RealtimeEvent(type=EventType.SYSTEM, content={"message": "ok"})
    await stream.publish(event)

    assert inner.published == [event]


def test_silent_event_stream_delegates_attribute_access():
    inner = FakeInnerStream()
    stream = SilentEventStream(inner)

    assert stream.name == "inner-stream"
