import contextlib
try:
    import msvcrt
    def init():
        import colorama
        colorama.just_fix_windows_console()

    def has_input():
        return msvcrt.kbhit()
    def get_input():
        char = msvcrt.getwch()
        while char == '\000' or char == '\xe0':
            char = msvcrt.getwch()
        return char
    set_terminal_raw = contextlib.nullcontext
except ImportError:
    import sys, termios, select, tty
    def init():
        pass
    def has_input():
        return select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], [])
    def get_input() -> str:
        return sys.stdin.read(1)
    @contextlib.contextmanager
    def set_terminal_raw():
        fd = sys.stdin.fileno()
        prev = None
        try:
            prev = tty.setraw(fd, termios.TCSANOW)
            yield
        finally:
            if prev is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, prev)


def get_key() -> None|str:
    with set_terminal_raw():
        if has_input():
            return get_input()
    return None

__all__ = ['get_key', 'init']