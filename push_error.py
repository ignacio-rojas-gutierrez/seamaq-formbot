
error_list: list[str] = []

def get_error_list() -> list[str]:
    return error_list

def clear_error_list():
    error_list.clear()

def push_error(error_message: str):
    error_list.append(error_message)

def push_error_if(condition: bool, error_message: str):
    if condition:
        push_error(error_message)