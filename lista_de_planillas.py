from dataclasses import dataclass, field
from typing import Iterator
import rto

"""
There can only be a limited number of RTO Planilla - for example, 20 -. The operating principle is a pointer will point to the newest RTO Planilla
over a limited size array. This means upon reaching the end of the array, the pointer will jump onto the first element, overriding it.
"""

@dataclass
class ListaPlanillas:
    array_size: int = 20
    rtos: list = field(init=False)                    # fixed-size array, None = empty slot
    pointer: int = field(default=-1, init=False)      # index of the newest planilla (-1 while empty)
    count: int = field(default=0, init=False)         # how many slots are filled (<= array_size)

    def __post_init__(self):
        if self.array_size <= 0:
            raise ValueError("array_size must be > 0")
        self.rtos = [None] * self.array_size

    # ---- writing -----------------------------------------------------------
    def add(self, planilla: "rto.RTO") -> None:
        """Store a planilla in the next slot. When the end of the array is reached
        the pointer wraps to index 0 and overwrites the oldest planilla."""
        self.pointer = (self.pointer + 1) % self.array_size
        self.rtos[self.pointer] = planilla
        self.count = min(self.count + 1, self.array_size)

    def clear(self) -> None:
        self.rtos = [None] * self.array_size
        self.pointer = -1
        self.count = 0

    # ---- reading -----------------------------------------------------------
    @property
    def newest(self) -> "rto.RTO | None":
        return self.rtos[self.pointer] if self.count else None

    @property
    def oldest(self) -> "rto.RTO | None":
        if not self.count:
            return None
        return self.rtos[(self.pointer + 1) % self.array_size] if self.is_full else self.rtos[0]

    @property
    def is_full(self) -> bool:
        return self.count == self.array_size

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator["rto.RTO"]:
        """Oldest -> newest."""
        start = (self.pointer + 1) % self.array_size if self.is_full else 0
        for i in range(self.count):
            yield self.rtos[(start + i) % self.array_size]

    def newest_first(self) -> Iterator["rto.RTO"]:
        for i in range(self.count):
            yield self.rtos[(self.pointer - i) % self.array_size]

    def __getitem__(self, i: int) -> "rto.RTO":
        """0 = oldest, -1 = newest (same order as iteration)."""
        if not -self.count <= i < self.count:
            raise IndexError(i)
        return list(self)[i]

    def find(self, dominio: str) -> "rto.RTO | None":
        """Newest planilla whose license plate matches (ignores case, spaces, dashes)."""
        clean = dominio.replace(" ", "").replace("-", "").upper()
        return next((p for p in self.newest_first() if p.dominio == clean), None)