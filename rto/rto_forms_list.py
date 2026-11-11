from dataclasses import dataclass, field
from typing import Iterator
import rto.entry as entry
import web_uia

"""
There can only be a limited number of RTO Planilla - for example, 20 -. The operating principle is a pointer will point to the newest RTO Planilla
over a limited size array. This means upon reaching the end of the array, the pointer will jump onto the first element, overriding it.
"""

"""
Clase representando la lista de planillas 
"""

class RTOFormsList:
    array_size: int = 20
    rtos: list = field(default_factory=list, init=False)                # fixed-size array, None = empty slot
    pointer: int = field(default=-1, init=False)      # index of the newest planilla (-1 while empty)
    count: int = field(default=0, init=False)         # how many slots are filled (<= array_size)

    def __post_init__(self):
        if self.array_size <= 0:
            raise ValueError("array_size must be > 0")
        self.rtos = [None] * self.array_size

    # def __init__(self, browser: str = "Chrome"):
    #     browser_win = web_uia.find_browser_window(browser)
    #     tab = web_uia.select_tab(browser_win, "Lista de Planillas")
    #     doc = web_uia.get_document(browser_win, "Lista de Planillas")
        
    #     data_items_raw = web_uia.get_data_items(doc)
    #     data_items_raw = data_items_raw[9::1] # skip header
    #     begin_indexes = [0]
        
    #     for i in range(len(data_items_raw)):
    #         if data_items_raw[i].text == '':
    #             begin_indexes.append(i + 1)
        
    #     for i, current_start in enumerate(begin_indexes):
    #         next_start = begin_indexes[i + 1] if i + 1 < len(begin_indexes) else len(data_items_raw)
        
    #         items = []
        
    #         for j in range(current_start, next_start):
    #             items.append(data_items_raw[j])
        
    #         new_entry = entry.RTOEntry(
    #             numero=items[0].text,
    #             dominio=items[1].text,
    #             linea=items[2].text,
    #             tipo_revision=items[3].text,
    #             inicio=items[4].text,
    #             resultado=items[5].text,
    #             accesible_buttons=[item for item in items[6:] if item.text != '']
    #         )
        
    #         self.add(new_entry)
    #         self.add()

    def __init__(self, array_size: int = 20):
        if array_size <= 0:
            raise ValueError("array_size must be > 0")
        self.array_size = array_size
        self.rtos: list = [None] * array_size   # fixed-size ring buffer, None = empty slot
        self.pointer = -1                       # index of the newest planilla
        self.count = 0                          


    def refresh(self, browser: str = "Chrome") -> None:
        """Reads 'Lista de Planillas' from the browser and refills the list."""
        browser_win = web_uia.find_browser_window(browser)
        if browser_win is None:
            raise RuntimeError(f"No {browser} window found.")
        if web_uia.select_tab(browser_win, "Lista de Planillas") is None:
            raise RuntimeError("Tab 'Lista de Planillas' not found.")
        doc = web_uia.get_page_document(browser_win, "Lista de Planillas")

        raw = web_uia.get_data_items(doc)[9:]    # skip header
        begin_indexes = [0]
        for i, item in enumerate(raw):
            if item.text == '' and i + 1 < len(raw):   # no start index past the end
                begin_indexes.append(i + 1)

        self.clear()
        for n, start in enumerate(begin_indexes):
            end = begin_indexes[n + 1] if n + 1 < len(begin_indexes) else len(raw)
            items = raw[start:end]
            if len(items) < 6:                   # incomplete row, skip it
                continue
            self.add(entry.RTOEntry(
                numero=items[0].text,
                dominio=items[1].text,
                linea=items[2].text,
                tipo_revision=items[3].text,
                inicio=items[4].text,
                resultado=items[5].text,
                accesible_buttons=[it for it in items[6:] if it.text != ''],
            ))


    # ---- writing -----------------------------------------------------------
    def add(self, planilla: "entry.RTOEntry") -> None:
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
    def newest(self) -> "entry.RTOEntry | None":
        return self.rtos[self.pointer] if self.count else None

    @property
    def oldest(self) -> "entry.RTOEntry | None":
        if not self.count:
            return None
        return self.rtos[(self.pointer + 1) % self.array_size] if self.is_full else self.rtos[0]

    @property
    def is_full(self) -> bool:
        return self.count == self.array_size

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator["entry.RTOEntry"]:
        """Oldest -> newest."""
        start = (self.pointer + 1) % self.array_size if self.is_full else 0
        for i in range(self.count):
            yield self.rtos[(start + i) % self.array_size]

    def newest_first(self) -> Iterator["entry.RTOEntry"]:
        for i in range(self.count):
            yield self.rtos[(self.pointer - i) % self.array_size]

    def __getitem__(self, i: int) -> "entry.RTOEntry":
        """0 = oldest, -1 = newest (same order as iteration)."""
        if not -self.count <= i < self.count:
            raise IndexError(i)
        return list(self)[i]

    def find(self, dominio: str) -> "entry.RTOEntry | None":
        """Newest planilla whose license plate matches (ignores case, spaces, dashes)."""
        clean = dominio.replace(" ", "").replace("-", "").upper()
        return next((p for p in self.newest_first() if p.dominio == clean), None)

    