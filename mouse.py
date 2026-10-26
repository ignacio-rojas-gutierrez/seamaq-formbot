import win32gui

class Mouse:
    @staticmethod
    def get_mouse_pos() -> tuple:
        """Mouse position in screen coordinates."""
        return win32gui.GetCursorPos()

    @staticmethod
    def get_mouse_pos_relative(handle: int, cursor: tuple | None = None) -> tuple:
        """Mouse position relative to the window's top-left corner (includes title bar and borders)."""
        mx, my = cursor or win32gui.GetCursorPos()
        left, top, _right, _bottom = win32gui.GetWindowRect(handle)
        return (mx - left, my - top)

    @staticmethod
    def get_mouse_pos_client(handle: int, cursor: tuple | None = None) -> tuple:
        """Mouse position relative to the client area (excludes title bar and borders).
        This is the one to use for clicking controls inside the window."""
        return win32gui.ScreenToClient(handle, cursor or win32gui.GetCursorPos())

    @staticmethod
    def get_distance_to_rect(point: tuple, rect: tuple) -> float:
        """Distance in pixels from a point to a (left, top, right, bottom) rectangle; 0 if inside."""
        x, y = point
        left, top, right, bottom = rect

        dx = max(left - x, 0, x - right)
        dy = max(top - y, 0, y - bottom)

        return (dx**2 + dy**2)**0.5