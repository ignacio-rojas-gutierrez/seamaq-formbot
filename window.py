import pywinauto
import win32gui
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

def get_window_info_by_title(window_title: str) -> WindowInfo:
    handles = findwindows.find_windows(title=window_title)
    if not handles:
        raise ValueError(f"Window not found: {window_title}")

    handle = handles[0]
    win = HwndWrapper(handle)
    show_state = win.get_show_state()  # 1 = normal, 2 = minimized, 3 = maximized
    rect = win.rectangle()

    return WindowInfo(
        title=win.window_text(),
        class_name=win.class_name(),
        process_id=win.process_id(),
        handle=handle,
        is_visible=win.is_visible(),
        is_enabled=win.is_enabled(),
        is_minimized=(show_state == 2),
        is_maximized=(show_state == 3),
        is_foreground=(win32gui.GetForegroundWindow() == handle),
        bounds=(rect.left, rect.top, rect.right, rect.bottom),
    )
        
    raise ValueError(f"Window not found: {window_title}")