from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict


@dataclass
class Timer:
    """Performance timer for measuring code execution duration"""

    start_time: float = field(default=0.0)
    end_time: float = field(default=0.0)

    @property
    def duration(self) -> float:
        """Calculate duration in seconds, handling active and stopped states"""
        if self.start_time == 0.0:
            return 0.0

        _end = self.end_time if self.end_time > 0.0 else perf_counter()
        return _end - self.start_time

    def begin(self) -> "Timer":
        """Mark the beginning of timing"""
        self.start_time = perf_counter()
        return self

    def end(self) -> float:
        """Mark the end of timing and return duration"""
        if self.start_time == 0.0:
            raise RuntimeError("Timer not started - call begin() first")

        self.end_time = perf_counter()
        return self.duration

    def reset(self) -> None:
        """Reset all timing markers"""
        self.start_time = 0.0
        self.end_time = 0.0

    def as_dict(self) -> Dict[str, float | None]:
        """Serialize timer state to dictionary"""
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration
        }
