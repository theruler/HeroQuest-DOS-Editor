import tkinter as tk
from tkinter import messagebox
import os
import sys
import traceback
from config import REQUIRED_FILES, resource_path
import subprocess
import importlib.util

def ensure_package(import_name, pip_name=None):
    pip_name = pip_name or import_name
    if importlib.util.find_spec(import_name) is not None:
        return

    print(f"'{pip_name}' not found, Installing...", flush=True)
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
    except FileNotFoundError:
        print("pip is not available.", flush=True)
        sys.exit(1)
    except subprocess.CalledProcessError:
        print(f"Error during installation of '{pip_name}'.", flush=True)
        sys.exit(1)
    importlib.invalidate_caches()
    if importlib.util.find_spec(import_name) is None:
        print(f"'{pip_name}' installed, but '{import_name}' doesn't seem to be importable.", flush=True)
        sys.exit(1)

if not getattr(sys, "frozen", False):
    ensure_package("PIL", pip_name="Pillow")
    ensure_package("tkinterdnd2", pip_name="tkinterdnd2")

try:
    from tkinterdnd2 import TkinterDnD
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

from editor import Editor

def check_required_files():
    return [f for f in REQUIRED_FILES
            if not os.path.exists(resource_path(f))]

def make_root():
    if _HAS_DND:
        try:
            return TkinterDnD.Tk()
        except Exception:
            pass
    return tk.Tk()

def main():
    try:
        missing = check_required_files()
        if missing:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Files missing", "\n".join(missing))
            root.destroy()
            sys.exit(1)

        root = make_root()
        app  = Editor(root)
        root.mainloop()

    except Exception:
        err = traceback.format_exc()
        try:
            traceback.print_exc()
        except Exception:
            pass
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Crash detected, contact the author", err)
            r.destroy()
        except Exception:
            pass

if __name__ == "__main__":
    main()
