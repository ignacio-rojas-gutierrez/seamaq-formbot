import pywinauto
from dataclasses import dataclass, field

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
    for any_window in pywinauto.findwindows.find_windows(title=window_title):
        window_handle = any_window
        window_info = pywinauto.application.Application().connect(handle=window_handle).any_window(handle=window_handle)
        
        return WindowInfo(
            title=window_info.window_text(),
            class_name=window_info.class_name(),
            process_id=window_info.process_id(),
            handle=window_handle,
            is_visible=window_info.is_visible(),
            is_enabled=window_info.is_enabled(),
            is_minimized=window_info.is_minimized(),
            is_maximized=window_info.is_maximized(),
            is_foreground=window_info.has_focus(),
            bounds=window_info.rectangle()
        )
        
    raise ValueError(f"Window not found: {window_title}")