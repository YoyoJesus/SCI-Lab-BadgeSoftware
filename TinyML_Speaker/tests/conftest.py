import gc
import tkinter as tk

import pytest


@pytest.fixture(scope='session')
def tk_interpreter():
    root = tk.Tk()
    root.withdraw()
    yield root
    gc.collect()
    root.destroy()


@pytest.fixture
def tk_window(tk_interpreter):
    window = tk.Toplevel(tk_interpreter)
    window.withdraw()
    yield window
    if window.winfo_exists():
        window.destroy()
    gc.collect()
