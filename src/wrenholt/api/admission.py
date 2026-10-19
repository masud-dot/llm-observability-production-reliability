"""Admission control (Chapter 17).

The process works on at most `size` answers at once, and keeps
`reserved` of them for critical actions. A question that finds no
room is not queued: it gets a degraded answer at once, or, for a
critical action, a 503 with Retry-After.
"""


class Admission:
    def __init__(self, size: int, reserved: int) -> None:
        self.size, self.reserved = size, reserved
        self.in_flight = 0

    def admit(self, request_class: str) -> bool:
        room = self.size
        if request_class != "critical_action":
            room -= self.reserved
        if self.in_flight >= room:
            return False
        self.in_flight += 1
        return True

    def release(self) -> None:
        self.in_flight -= 1
