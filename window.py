"""window.py - helpers to inspect Windows windows and controls (pywinauto + win32gui)."""

import re
from dataclasses import dataclass, field

import win32con
import win32gui
from pywinauto import findwindows
from pywinauto.controls.hwndwrapper import HwndWrapper


@dataclass
class WindowInfo:
    title: str = ""
    class_name: str = ""
    process_id: int = 0
    handle: int = 0
    is_visible: bool = False
    is_enabled: bool = False
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    bounds: tuple = ()
    mouse_pos_relative: tuple = ()
    mouse_pos_client: tuple = ()
    distance_to_mouse: float = 0.0
    is_closest_to_mouse: bool = False
    children: list = field(default_factory=list)   # list[WindowInfo]


# ---- finding windows -------------------------------------------------------
def find_handles(title: str, regex: bool = False) -> list[int]:
    """Handles of every top-level window whose title matches (prefix match if not regex)."""
    pattern = title if regex else re.escape(title)
    return findwindows.find_windows(title_re=pattern)


def find_handle(title: str, regex: bool = False) -> int | None:
    """Handle of the first window matching the title, or None."""
    handles = find_handles(title, regex)
    return handles[0] if handles else None


def get_top_windows() -> list[tuple[int, str]]:
    """[(handle, title), ...] for every visible top-level window that has a title."""
    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append((hwnd, title))

    win32gui.EnumWindows(callback, None)
    return result


# ---- mouse -----------------------------------------------------------------
def get_mouse_pos() -> tuple:
    """Mouse position in screen coordinates."""
    return win32gui.GetCursorPos()


def get_mouse_pos_relative(handle: int, cursor: tuple | None = None) -> tuple:
    """Mouse position relative to the window's top-left corner (includes title bar and borders)."""
    mx, my = cursor or win32gui.GetCursorPos()
    left, top, _right, _bottom = win32gui.GetWindowRect(handle)
    return (mx - left, my - top)


def get_mouse_pos_client(handle: int, cursor: tuple | None = None) -> tuple:
    """Mouse position relative to the client area (excludes title bar and borders).
    This is the one to use for clicking controls inside the window."""
    return win32gui.ScreenToClient(handle, cursor or win32gui.GetCursorPos())


def get_distance_to_rect(point: tuple, rect: tuple) -> float:
    """Distance in pixels from a point to a (left, top, right, bottom) rectangle; 0 if inside."""
    x, y = point
    left, top, right, bottom = rect

    dx = max(left - x, 0, x - right)
    dy = max(top - y, 0, y - bottom)

    return (dx**2 + dy**2)**0.5


# ---- window info -----------------------------------------------------------
def get_window_by_wrapper(wrapper, child_depth: int) -> WindowInfo:
    """Build a WindowInfo from a pywinauto wrapper (window or child control).
    Also accepts a WindowSpecification, e.g. app.window(...) or dlg.child_window(...)."""
    if hasattr(wrapper, "wrapper_object"):
        wrapper = wrapper.wrapper_object()

    handle = wrapper.handle
    show_state = wrapper.get_show_state()
    rect = wrapper.rectangle()
    cursor = win32gui.GetCursorPos()      # read once so both mouse positions agree

    return WindowInfo(
        title=wrapper.window_text(),
        class_name=wrapper.class_name(),
        process_id=wrapper.process_id(),
        handle=handle,
        is_visible=wrapper.is_visible(),
        is_enabled=wrapper.is_enabled(),
        is_minimized=(show_state == win32con.SW_SHOWMINIMIZED),
        is_maximized=(show_state == win32con.SW_SHOWMAXIMIZED),
        is_foreground=(win32gui.GetForegroundWindow() == handle),
        bounds=(rect.left, rect.top, rect.right, rect.bottom),
        mouse_pos_relative=get_mouse_pos_relative(handle, cursor),
        mouse_pos_client=get_mouse_pos_client(handle, cursor),
        distance_to_mouse=round(get_distance_to_rect(cursor, (rect.left, rect.top, rect.right, rect.bottom)), 1),
        children=_build_children(wrapper, child_depth),
    )



def _build_children(wrapper, child_depth: int) -> list[WindowInfo]:
    if child_depth <= 0:
        return []
    return [get_window_by_wrapper(child, child_depth - 1) for child in wrapper.children()]



def get_window_info(handle: int, child_depth: int = 0) -> WindowInfo:
    return get_window_by_wrapper(HwndWrapper(handle), child_depth)



def get_child_windows_of(handle: int, depth: int = 1) -> list[WindowInfo]:
    return [get_window_by_wrapper(child, depth - 1) for child in HwndWrapper(handle).children()]


def get_window_info_by_title(window_title: str, regex: bool = False) -> WindowInfo | None:
    handle = find_handle(window_title, regex)
    return get_window_info(handle) if handle else None


def get_child_windows(window_title: str, regex: bool = False, depth: int = 1) -> list[WindowInfo]:
    handle = find_handle(window_title, regex)
    return get_child_windows_of(handle, depth) if handle else []