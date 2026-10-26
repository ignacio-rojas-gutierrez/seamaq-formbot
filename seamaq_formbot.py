"""seamaq_formbot.py - main loop for the GigaTest form-filling bot."""

from dataclasses import dataclass, field
from time import sleep

import keyboard

import push_error
import window
from ui_dearpygui import StateWindow

# Default window to target. Matched as a literal prefix (see window._find_handles),
# so do not put regex like ".*" here. It can be changed at runtime from the UI dropdown.
DEFAULT_TARGET_TITLE = "GigaTest"
FRAME_TIME = 1 / 60
CHILD_DEPTH = 4   # levels of child controls to scan (1 = direct children only)

@dataclass
class State:
    should_exit: bool = False
    mouse_pos: tuple = ()
    target_window_title: str = DEFAULT_TARGET_TITLE
    target_window: "window.WindowInfo | None" = None
    test_windows_array: list = field(default_factory=list)
    error_list: list[str] = field(default_factory=list)
    counter: int = 0


class FormBot:
    def __init__(self):
        self.state = State()
        self.ui: StateWindow | None = None

    # ---- lifecycle ---------------------------------------------------------
    def run(self):
        self._start()
        try:
            while not self.state.should_exit:
                self._update()
                sleep(FRAME_TIME)
        finally:
            self._stop()

    def _start(self):
        keyboard.on_press_key("esc", lambda _e: self.request_exit())
        self.state.target_window = window.get_window_info_by_title(self.state.target_window_title)
        self.ui = StateWindow(
            self.state,
            on_close=self.request_exit,
            window_provider=window.get_top_windows,
            on_window_selected=self.set_target_title,
        )
        self.ui.log("Application Started")

    def _stop(self):
        keyboard.unhook_all()
        if self.ui:
            self.ui.close()

    def request_exit(self):
        self.state.should_exit = True

    # ---- target window -----------------------------------------------------
    def set_target_title(self, title: str):
        self.state.target_window_title = title

    def _find_target_window(self):
        return window.get_window_info_by_title(self.state.target_window_title)

    # ---- per-frame update --------------------------------------------------
    def _update(self):
        self._update_state()
        self._check_errors()
        self.ui.update()
        push_error.clear_error_list()      # errors only live for one frame

    def _update_state(self):
        s = self.state
        handle = self._find_target_handle()          # one search per frame
        s.target_window = window.get_window_info(handle) if handle else None
        s.test_windows_array = window.get_child_windows_of(handle, CHILD_DEPTH) if handle else []
        s.mouse_pos = window.get_mouse_pos()
        s.counter += 1

    def _check_errors(self):
        push_error.push_error_if(
            self.state.target_window is None,
            f"Target window '{self.state.target_window_title}' not found.",
        )
        self.state.error_list = list(push_error.get_error_list())  # copy, not alias

    def _find_target_handle(self):
        return window.find_handle(self.state.target_window_title)  


def run():
    FormBot().run()