"""
ui.py - live state window using Dear PyGui.

Same API as before: give it YOUR state dataclass and call update() once per
frame from your main loop. Nested dataclasses/objects and lists of objects are
shown as collapsible tree nodes; every field you add to State shows up
automatically.

    import ui

    state_window = ui.StateWindow(state, on_close=request_exit)
    while not should_exit():
        state_window.update()
    state_window.close()
"""

import dataclasses
import time
from collections import deque

import dearpygui.dearpygui as dpg

_LEAF_TYPES = (str, int, float, bool, bytes, type(None), list, tuple, dict, set)

NAME_COLOR = (150, 190, 255, 255)
GRAY = (150, 150, 150, 255)
VALUE_COLORS = {
    "True": (90, 200, 90, 255),
    "False": (230, 90, 90, 255),
    "None": GRAY,
}
DEFAULT_VALUE_COLOR = (230, 230, 230, 255)


def _children(obj):
    """Return [(name, value), ...] if obj should be expanded, else None (leaf)."""
    if isinstance(obj, (list, tuple)):
        if obj and any(_children(v) is not None for v in obj):
            return [(f"[{i}]", v) for i, v in enumerate(obj)]
        return None
    if isinstance(obj, _LEAF_TYPES) or isinstance(obj, type):
        return None
    if dataclasses.is_dataclass(obj):
        return [(f.name, getattr(obj, f.name, None)) for f in dataclasses.fields(obj)]
    if hasattr(obj, "__dict__"):
        items = [(k, v) for k, v in vars(obj).items() if not k.startswith("_")]
        return items or None
    return None


def _summary(name, value):
    """Short text shown next to a group header."""
    if isinstance(value, (list, tuple)):
        return f"({len(value)} items)"
    if name.startswith("["):
        parts = []
        title = getattr(value, "title", "")
        class_name = getattr(value, "class_name", "")
        if title:
            parts.append(f'"{title}"')
        if class_name:
            parts.append(f"<{class_name}>")
        if getattr(value, "is_closest_to_mouse", False):
            parts.append("<-- closest")
        return " ".join(parts)
    return ""


def build_rows(obj, path="", depth=0, max_depth=16):
    """Flatten a nested state into rows: (path, name, kind, text, depth)."""
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
    def __init__(self, state, title="Seamaq", on_close=None, start_open=True, window_provider=None, on_window_selected=None):
        self.state = state
        self.closed = False
        self._on_close = on_close
        self._start_open = start_open
        self._window_provider = window_provider          # () -> [(handle, title), ...]
        self._on_window_selected = on_window_selected    # (title) -> None
        self._order = []          # [(path, kind, depth)] currently built
        self._items = {}          # path -> {"kind", "tag", "text"}
        self._open = {}           # path -> bool, remembered across rebuilds
        self._log_ids = deque()   # text item ids in the log, oldest first
        self._log_pending = []
        self._log_max = 500
        self._frames = 0
        self._last_fps_time = time.time()

        dpg.create_context()
        dpg.create_viewport(title=title, width=520, height=520, always_on_top=True)

        with dpg.window() as main_window:
            self._fps_label = dpg.add_text("", color=GRAY)
            with dpg.tab_bar():
                with dpg.tab(label="Interface"):
                    with dpg.group(horizontal=True):
                        self._window_combo = dpg.add_combo(
                            items=[], width=380, callback=self._on_combo_changed)
                        dpg.add_button(label="Refresh", callback=self.refresh_windows)
                        self._selected_label = dpg.add_text("Selected: none", color=GRAY)
                with dpg.tab(label="State"):
                    self._state_box = dpg.add_child_window(border=False)
                with dpg.tab(label="Log"):
                    self._log_box = dpg.add_child_window(border=False)

        dpg.set_primary_window(main_window, True)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        self.refresh_windows()

    # ---- public API --------------------------------------------------------
    def log(self, message):
        self._log_pending.append(f"{time.strftime('%H:%M:%S')}  {message}")

    def update(self):
        """Call once per frame from your main loop."""
        if self.closed:
            return
        if not dpg.is_dearpygui_running():   # user closed the window
            self.close()
            return
        self._draw_state()
        self._draw_log()
        self._draw_fps()
        dpg.render_dearpygui_frame()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._on_close:
            self._on_close()
        try:
            dpg.destroy_context()
        except Exception:
            pass

    def refresh_windows(self, *_):
        """Reload the dropdown with the currently open top-level windows."""
        if not self._window_provider:
            return
        self._window_labels = {
            f"{title}  (0x{hwnd:X})": title
            for hwnd, title in sorted(self._window_provider(), key=lambda w: w[1].lower())
        }
        dpg.configure_item(self._window_combo, items=list(self._window_labels))

    def _on_combo_changed(self, _sender, label):
        title = self._window_labels.get(label)
        if title is None:
            return
        dpg.set_value(self._selected_label, f"Selected: {title}")
        self.log(f"Target window set to '{title}'")
        if self._on_window_selected:
            self._on_window_selected(title)
    

    # ---- drawing -----------------------------------------------------------
    def _remember_open(self):
        for path, item in self._items.items():
            if item["kind"] == "group":
                self._open[path] = dpg.get_value(item["tag"])

    def _rebuild(self, rows):
        self._remember_open()
        dpg.delete_item(self._state_box, children_only=True)
        self._items.clear()

        stack = [self._state_box]            # stack[depth] = parent container
        for path, name, kind, _text, depth in rows:
            del stack[depth + 1:]
            parent = stack[depth]
            if kind == "group":
                default_open = self._open.get(path, depth == 0 and self._start_open)
                node = dpg.add_tree_node(label=name, default_open=default_open, parent=parent)
                stack.append(node)
                self._items[path] = {"kind": kind, "tag": node, "text": None, "name": name}
            else:
                line = dpg.add_group(horizontal=True, parent=parent)
                dpg.add_text(name + ":", color=NAME_COLOR, parent=line)
                value = dpg.add_text("", parent=line)
                self._items[path] = {"kind": kind, "tag": value, "text": None, "name": name}

    def _draw_state(self):
        rows = build_rows(self.state)
        order = [(r[0], r[2], r[4]) for r in rows]
        if order != self._order:             # structure changed -> rebuild
            self._rebuild(rows)
            self._order = order

        for path, name, kind, text, depth in rows:
            item = self._items[path]
            shown = f"{name}  {text}" if (kind == "group" and text) else text if kind == "leaf" else name
            if item["text"] == shown:
                continue
            item["text"] = shown
            if kind == "group":
                dpg.configure_item(item["tag"], label=shown)
            else:
                dpg.set_value(item["tag"], text)
                dpg.configure_item(item["tag"], color=VALUE_COLORS.get(text, DEFAULT_VALUE_COLOR))

    def _draw_log(self):
        if not self._log_pending:
            return
        at_bottom = dpg.get_y_scroll(self._log_box) >= dpg.get_y_scroll_max(self._log_box) - 1
        for line in self._log_pending:
            if len(self._log_ids) >= self._log_max:
                dpg.delete_item(self._log_ids.popleft())
            self._log_ids.append(dpg.add_text(line, parent=self._log_box))
        self._log_pending.clear()
        if at_bottom:
            dpg.set_y_scroll(self._log_box, -1.0)   # follow the newest line

    def _draw_fps(self):
        self._frames += 1
        now = time.time()
        if now - self._last_fps_time >= 1.0:
            fps = self._frames / (now - self._last_fps_time)
            self._frames = 0
            self._last_fps_time = now
            dpg.set_value(self._fps_label, f"{fps:.0f} FPS")


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