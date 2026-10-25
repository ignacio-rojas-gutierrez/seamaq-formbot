import win32gui
import re

from dataclasses import dataclass, field
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
    bounds: tuple = field(default_factory=tuple)
    mouse_pos_relative: tuple = field(default_factory=tuple)
    mouse_pos_client: tuple = field(default_factory=tuple)


def _find_handles(title: str, regex: bool = False) -> list[int]:
      if regex:
          return findwindows.find_windows(title_re=title)
      return findwindows.find_windows(title_re=re.escape(title))


def get_window_by_wrapper(wrapper:HwndWrapper) -> WindowInfo:
    """Build a WindowInfo from a pywinauto wrapper (window or child control).
    Also accepts a WindowSpecification, e.g. app.window(...) or dlg.child_window(...)."""
    if hasattr(wrapper, "wrapper_object"):
        wrapper = wrapper.wrapper_object()

    handle = wrapper.handle
    show_state = wrapper.get_show_state()  # 1 = normal, 2 = minimized, 3 = maximized
    rect = wrapper.rectangle()

    return WindowInfo(
        title=wrapper.window_text(),
        class_name=wrapper.class_name(),
        process_id=wrapper.process_id(),
        handle=handle,
        is_visible=wrapper.is_visible(),
        is_enabled=wrapper.is_enabled(),
        is_minimized=(show_state == 2),
        is_maximized=(show_state == 3),
        is_foreground=(win32gui.GetForegroundWindow() == handle),
        bounds=(rect.left, rect.top, rect.right, rect.bottom),
        mouse_pos_relative=get_mouse_pos_relative(handle),
        mouse_pos_client=get_mouse_pos_client(handle)
    )

def get_window_info_by_title(window_title: str) -> WindowInfo:
    handles = _find_handles(window_title, regex=False)

    if not handles:
        return None

    return get_window_by_wrapper(HwndWrapper(handles[0]))

def get_child_windows(window_title: str) -> list:
    """WindowInfo for every child control of the window with this title."""
    handles = _find_handles(window_title, regex=False)

    if len(handles) == 0:
        return []
    
    parent = HwndWrapper(handles[0])
    return [get_window_by_wrapper(child) for child in parent.children()]


def get_mouse_pos() -> tuple:
    """Mouse position in screen coordinates."""
    return win32gui.GetCursorPos()


def get_mouse_pos_relative(handle: int) -> tuple:
    """Mouse position relative to the window's top-left corner (includes title bar and borders)."""
    mx, my = win32gui.GetCursorPos()
    left, top, _right, _bottom = win32gui.GetWindowRect(handle)
    return (mx - left, my - top)


def get_mouse_pos_client(handle: int) -> tuple:
    """Mouse position relative to the client area (excludes title bar and borders).
    This is the one to use for clicking controls inside the window."""
    return win32gui.ScreenToClient(handle, win32gui.GetCursorPos())


def get_top_windows() -> list:
    """[(handle, title), ...] for every visible top-level window that has a title."""
    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append((hwnd, title))

    win32gui.EnumWindows(callback, None)
    return result