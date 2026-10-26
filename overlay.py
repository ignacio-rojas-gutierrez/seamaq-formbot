"""overlay.py - transparent, click-through window that draws rectangles over the screen.

    overlay = Overlay()
    overlay.draw([((left, top, right, bottom), "red")])   # call once per frame
    overlay.close()

Rectangles are in screen coordinates (the same as WindowInfo.bounds).
"""

import ctypes
import tkinter as tk

# Without this, Windows display scaling (125%, 150%...) shifts the rectangles.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020     # mouse clicks pass through the overlay
WS_EX_TOOLWINDOW = 0x00000080      # no taskbar button
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
TRANSPARENT_COLOR = "#010101"      # anything drawn in this color is see-through


class Overlay:
    def __init__(self, line_width: int = 3):
        self.closed = False
        self._line_width = line_width

        user32 = ctypes.windll.user32
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)    # covers every monitor
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        self._origin = (x, y)

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        self.root.geometry(f"{w}x{h}{x:+d}{y:+d}")

        self._canvas = tk.Canvas(self.root, bg=TRANSPARENT_COLOR, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        self.root.update_idletasks()
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)

    def draw(self, rects):
        """rects: [((left, top, right, bottom), color), ...]. Replaces what was drawn before."""
        if self.closed:
            return
        ox, oy = self._origin
        try:
            self._canvas.delete("all")
            for (left, top, right, bottom), color in rects:
                self._canvas.create_rectangle(
                    left - ox, top - oy, right - ox, bottom - oy,
                    outline=color, width=self._line_width)
            self.root.update()
        except tk.TclError:           # window was destroyed
            self.closed = True

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass