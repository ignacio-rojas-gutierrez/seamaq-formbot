from time import sleep
import keyboard

from dataclasses import dataclass, field

from ui_dearpygui import StateWindow
import window as window
import push_error as push_error
from pywinauto import Application

# constants
TARGET_WINDOW_TITLE = "GigaTest.*"  # Change this to the title of the window you want to target



def run():
    initialize()
    while not should_exit():
        update()
        sleep(1/30)


@dataclass
class State:
    should_exit: bool = False
    mouse_pos: tuple = field(default_factory=tuple)
    target_window_title : str = TARGET_WINDOW_TITLE
    target_window: 'window.WindowInfo' = None
    test_windows_array: list = field(default_factory=list)
    error_list: list[str] = field(default_factory=list)
    counter: int = 0




state : 'State' = None
state_window : 'StateWindow' = None


def set_target_title(title: str):
    get_state().target_window_title = title


def get_target_window():
    state.target_window = window.get_window_info_by_title(TARGET_WINDOW_TITLE)
    return get_state().target_window


def get_state():
    global state
    if state is None: # Create state if it's null
        state = State()
    
    return state

def should_exit() -> bool:
    return get_state().should_exit

def initialize_keyboard_listener():
    def on_key_event(event):
        if event.name == 'esc':
            get_state().should_exit = True

    keyboard.on_press(on_key_event)


def get_state_window():
    global state_window

    if state_window is None: # Create state window if it's null
        current_state = get_state()
        state_window = StateWindow(
            current_state,
            on_close=lambda: setattr(current_state, "should_exit", True),
            window_provider=window.get_top_windows,
            on_window_selected=set_target_title
            )
        push_error.push_error_if(state_window is None, "State Window not initialized.")

    return state_window

def update_state():
    get_state().target_window = get_target_window()
    get_state().test_windows_array = window.get_child_windows(TARGET_WINDOW_TITLE)
    get_state().mouse_pos = window.get_mouse_pos()

    get_state().counter += 1
    
def update_state_window():
    get_state_window().update()


def setup_state():
    global state
    state = get_state()
    get_state().target_window = get_target_window()


def setup_state_window():
    global state_window
    state_window = get_state_window()


def initialize():
    initialize_keyboard_listener()
    setup_state()
    setup_state_window()

    state_window.log("Application Started");

def update_error_list() -> list[str]:
    state.error_list = push_error.get_error_list()

def update():
    update_state()

    push_error.push_error_if(
        state.target_window is None, f"Target window '{TARGET_WINDOW_TITLE}' not found.")

    update_error_list()

    update_state_window()
    end_frame()

def end_frame():
    push_error.clear_error_list()