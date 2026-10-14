from time import sleep
import keyboard

from dataclasses import dataclass, field

from ui import StateWindow
import window as window

# constants
TARGET_WINDOW_TITLE = "File Explorer"  # Change this to the title of the window you want to target

@dataclass
class State:
    should_exit: bool = False
    target_window: 'window.WindowInfo' = None
    test_windows_array: list = field(default_factory=list)
    counter: int = 0

state : 'State' = None
state_window : 'StateWindow' = None

def get_target_window():
    if state.target_window is None:
        state.target_window = window.get_window_info_by_title(TARGET_WINDOW_TITLE)

    return get_state().target_window

def get_state():
    global state
    if state is None:
        state = State()

    if state is None:
        raise RuntimeError("State is not initialized.")
    
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
    if state_window is None:
        current_state = get_state()
        state_window = StateWindow(current_state, on_close=lambda: setattr(current_state, "should_exit", True))

    if state_window is None:
        raise RuntimeError("State window is not initialized.")
    
    return state_window
    
def update_state_window():
    get_state_window().update()

def setup_state():
    state = get_state()
    state.target_window = get_target_window()

def initialize():
    initialize_keyboard_listener()
    
    state = get_state()
    state_window = get_state_window()

    setup_state()

# Entry
def main():
    initialize()
    state_window.log("Application started. Press ESC to exit.")
    while not should_exit():
        update_state_window()
        sleep(1/60) # Run at 60 FPS


if __name__ == "__main__":
    main()