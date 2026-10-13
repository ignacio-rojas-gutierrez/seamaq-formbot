"""
ui.py - live state window, imgui style.

No threads and no extra state object: you give it YOUR state dataclass and call
update() once per frame from your main loop. Every frame it re-reads the state
and redraws it. Any field you add to your State shows up automatically.

- Nested dataclasses / objects (like target_window -> WindowInfo) are shown as
  collapsible sections: click the header to open or close it.
- Lists of objects (like test_windows_array) are shown as a collapsible list,
  one collapsible entry per item, labelled with its title and class name.
- The State tab scrolls (mouse wheel or scrollbar) when there are many rows.

    import ui

    state_window = ui.StateWindow(state, on_close=request_exit)
    while not should_exit():
        state_window.update()
        ...
    state_window.close()
"""

import dataclasses
import time
import tkinter as tk
from collections import deque
from tkinter import ttk

_LEAF_TYPES = (str, int, float, bool, bytes, type(None), list, tuple, dict, set)
INDENT_PX = 18


def _children(obj):
    """Return [(name, value), ...] if obj should be expanded, else None (leaf)."""
    if isinstance(obj, (list, tuple)):
        # Only expand lists that contain objects; a plain list of numbers stays one line.
        if obj and any(_children(v) is not None for v in obj):
            return [(f"[{i}]", v) for i, v in enumerate(obj)]
        return None
    if isinstance(obj, _LEAF_TYPES) or isinstance(obj, type):
        return None
    if dataclasses.is_dataclass(obj):
        return [(f.name, getattr(obj, f.name, None)) for f in dataclasses.fields(obj)]
    if hasattr(obj, "__dict__"):
        items = [(k, v) for k, v in vars(obj).items() if not k.startswith("_")]
        return items or None          # e.g. a RECT with no plain attributes -> leaf
    return None


def _summary(name, value):
    """Short text shown next to a group header."""
    if isinstance(value, (list, tuple)):
        return f"({len(value)} items)"
    if name.startswith("["):          # an item of a list: show title / class name
        parts = []
        title = getattr(value, "title", "")
        class_name = getattr(value, "class_name", "")
        if title:
            parts.append(f'"{title}"')
        if class_name:
            parts.append(f"<{class_name}>")
        return " ".join(parts)
    return ""


def build_rows(obj, path="", depth=0, max_depth=5):
    """Flatten a nested state into rows: (path, name, kind, text, depth).
    kind is "group" (collapsible header, text = summary) or "leaf" (text = value)."""
    rows = []
    for name, value in _children(obj) or []:
        child_path = f"{path}{name}"
        expandable = depth + 1 < max_depth and _children(value) is not None
        if expandable:
            rows.append((child_path, name, "group", _summary(name, value), depth))
            rows.extend(build_rows(value, child_path + ".", depth + 1, max_depth))
        else:
            text = repr(value) if isinstance(value, str) else str(value)
            rows.append((child_path, name, "leaf", text, depth))
    return rows


class StateWindow:
    def __init__(self, state, title="Program state", on_close=None, start_open=True):
        self.state = state
        self.closed = False
        self._on_close = on_close
        self._start_open = start_open
        self._collapsed = {}      # group path -> True/False (set when the user clicks)
        self._order = []          # visible row paths currently on screen
        self._widgets = {}        # path -> (name_label, value_label or None)
        self._log = deque(maxlen=500)
        self._log_dirty = True
        self._frames = 0
        self._last_fps_time = time.time()

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("520x520")
        self.root.attributes("-topmost", True)   # stay visible over the target program
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        # State tab: a scrollable canvas that holds the grid of rows
        state_tab = ttk.Frame(notebook)
        notebook.add(state_tab, text="State")
        self._canvas = tk.Canvas(state_tab, highlightthickness=0)
        vbar = ttk.Scrollbar(state_tab, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._state_tab = ttk.Frame(self._canvas, padding=10)
        self._state_tab.columnconfigure(1, weight=1)
        inner_id = self._canvas.create_window((0, 0), window=self._state_tab, anchor="nw")
        self._state_tab.bind(
            "<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>", lambda e: self._canvas.itemconfigure(inner_id, width=e.width))
        self.root.bind_all(
            "<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"))

        # Log tab
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="Log")
        self._log_text = tk.Text(log_tab, state="disabled", wrap="none", font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_tab, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log_text.pack(fill="both", expand=True)

        self._fps_label = ttk.Label(self.root, text="", foreground="gray")
        self._fps_label.pack(anchor="e", padx=8, pady=(0, 4))

    # ---- public API --------------------------------------------------------
    def log(self, message):
        self._log.append(f"{time.strftime('%H:%M:%S')}  {message}")
        self._log_dirty = True

    def update(self):
        """Call once per frame from your main loop."""
        if self.closed:
            return
        try:
            self._draw_state()
            self._draw_log()
            self._draw_fps()
            self.root.update()
        except tk.TclError:           # window was destroyed
            self.closed = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._on_close:
            self._on_close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ---- drawing -----------------------------------------------------------
    def _is_collapsed(self, path, depth):
        # Default: top-level sections follow start_open; nested ones (the items
        # of a list) start closed so a long list stays readable.
        return self._collapsed.get(path, depth >= 1 or not self._start_open)

    def _toggle(self, path, depth):
        self._collapsed[path] = not self._is_collapsed(path, depth)

    def _visible_rows(self, rows):
        """Drop the rows that sit inside a collapsed group."""
        visible, hide_below = [], None
        for row in rows:
            path, name, kind, text, depth = row
            if hide_below is not None:
                if depth > hide_below:
                    continue
                hide_below = None
            visible.append(row)
            if kind == "group" and self._is_collapsed(path, depth):
                hide_below = depth
        return visible

    def _draw_state(self):
        rows = self._visible_rows(build_rows(self.state))
        paths = [r[0] for r in rows]

        if paths != self._order:      # structure changed -> rebuild the grid
            for name_label, value_label in self._widgets.values():
                name_label.destroy()
                if value_label:
                    value_label.destroy()
            self._widgets.clear()
            for i, (path, name, kind, text, depth) in enumerate(rows):
                pad = (depth * INDENT_PX, 0)
                if kind == "group":
                    header = ttk.Label(self._state_tab, cursor="hand2",
                                       font=("Segoe UI", 9, "bold"), foreground="#1a5fb4")
                    header.grid(row=i, column=0, columnspan=2, sticky="w", padx=pad, pady=(6, 2))
                    header.bind("<Button-1>", lambda _e, p=path, d=depth: self._toggle(p, d))
                    self._widgets[path] = (header, None)
                else:
                    name_label = ttk.Label(self._state_tab, text=name + ":",
                                           font=("Segoe UI", 9, "bold"))
                    value_label = ttk.Label(self._state_tab, anchor="w", wraplength=260)
                    name_label.grid(row=i, column=0, sticky="nw", padx=pad, pady=2)
                    value_label.grid(row=i, column=1, sticky="we", padx=(10, 0), pady=2)
                    self._widgets[path] = (name_label, value_label)
            self._order = paths

        for path, name, kind, text, depth in rows:
            name_label, value_label = self._widgets[path]
            if kind == "group":
                arrow = "\u25b6" if self._is_collapsed(path, depth) else "\u25bc"
                label_text = f"{arrow} {name}" + (f"  {text}" if text else "")
                if str(name_label.cget("text")) != label_text:
                    name_label.configure(text=label_text)
            else:
                if str(value_label.cget("text")) != text:
                    value_label.configure(text=text)
                color = {"True": "green", "False": "red", "None": "gray"}.get(text, "black")
                value_label.configure(foreground=color)

    def _draw_log(self):
        if not self._log_dirty:
            return
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.insert("end", "\n".join(self._log))
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
        self._log_dirty = False

    def _draw_fps(self):
        self._frames += 1
        now = time.time()
        if now - self._last_fps_time >= 1.0:
            fps = self._frames / (now - self._last_fps_time)
            self._frames = 0
            self._last_fps_time = now
            self._fps_label.configure(text=f"{fps:.0f} FPS")

# Demo: python ui.py
if __name__ == "__main__":
    @dataclasses.dataclass
    class WindowInfo:
        title: str = ""
        class_name: str = ""
        process_id: int = 4242
        handle: int = 0
        is_visible: bool = True
        is_foreground: bool = False
        bounds: tuple = (0, 0, 800, 600)

    @dataclasses.dataclass
    class DemoState:
        should_exit: bool = False
        target_window: WindowInfo = None
        test_windows_array: list = dataclasses.field(default_factory=list)
        counter: int = 0

    demo = DemoState(
        target_window=WindowInfo(title="GigaTest", class_name="TForm1", handle=0x1234),
        test_windows_array=[
            WindowInfo(title="Cantidad", class_name="TLabel", handle=0x2001),
            WindowInfo(class_name="TEdit", handle=0x2002),
            WindowInfo(title="Aceptar", class_name="TButton", handle=0x2003),
        ],
    )
    win = StateWindow(demo, on_close=lambda: setattr(demo, "should_exit", True))
    win.log("demo started")
    while not demo.should_exit:
        demo.counter += 1
        demo.target_window.is_foreground = (demo.counter // 60) % 2 == 0
        win.update()
        time.sleep(1 / 60)