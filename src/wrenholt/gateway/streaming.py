"""Timer arithmetic for streamed responses (Chapter 8).

A chunk counts when it carries output text. Time to first chunk
runs from the start of the operation to the first such chunk, so
time lost to failed attempts counts, as it does for the customer.
Time per output chunk is recorded for each later chunk, from the
end of the previous chunk to the end of this one.
"""

from dataclasses import dataclass, field


@dataclass
class StreamClock:
    started: float
    first: float | None = None
    last: float | None = None
    gaps: list[float] = field(default_factory=list)

    def chunk(self, now: float) -> float | None:
        """Record one chunk; return its time per output chunk, or
        None for the first chunk."""
        gap = None if self.last is None else now - self.last
        if gap is None:
            self.first = now
        else:
            self.gaps.append(gap)
        self.last = now
        return gap

    @property
    def to_first(self) -> float | None:
        return (
            None if self.first is None else self.first - self.started
        )

    @property
    def chunks(self) -> int:
        return 0 if self.first is None else len(self.gaps) + 1

    def total(self, now: float) -> float:
        return now - self.started
