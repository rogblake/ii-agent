import pytest

import ii_agent.utils.timer as timer_module
from ii_agent.utils.timer import Timer


def test_duration_is_zero_before_begin():
    timer = Timer()
    assert timer.duration == 0.0


def test_duration_while_running_uses_current_perf_counter(monkeypatch):
    values = iter([2.0, 5.0])
    monkeypatch.setattr(timer_module, "perf_counter", lambda: next(values))

    timer = Timer().begin()

    assert timer.duration == pytest.approx(3.0)


def test_end_returns_duration_and_serializes(monkeypatch):
    values = iter([10.0, 13.5])
    monkeypatch.setattr(timer_module, "perf_counter", lambda: next(values))

    timer = Timer().begin()
    duration = timer.end()
    serialized = timer.as_dict()

    assert duration == pytest.approx(3.5)
    assert serialized["start_time"] == 10.0
    assert serialized["end_time"] == 13.5
    assert serialized["duration"] == pytest.approx(3.5)


def test_end_raises_when_timer_not_started():
    with pytest.raises(RuntimeError, match="Timer not started"):
        Timer().end()


def test_reset_clears_timer_state(monkeypatch):
    values = iter([4.0, 9.0])
    monkeypatch.setattr(timer_module, "perf_counter", lambda: next(values))

    timer = Timer().begin()
    _ = timer.end()

    timer.reset()

    assert timer.start_time == 0.0
    assert timer.end_time == 0.0
    assert timer.duration == 0.0
