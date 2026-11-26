import os
import subprocess
import sys
from pathlib import Path

PICK_FOLDER_TK = """
import tkinter, tkinter.filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(tkinter.filedialog.askdirectory(title="Destination") or "")
"""


def data_dir(app: str) -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / app
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming") / app
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / app


def pick_folder() -> str:
    if sys.platform == "darwin":
        command = ["osascript", "-e", 'POSIX path of (choose folder with prompt "Destination")']
    else:
        command = [sys.executable, "-c", PICK_FOLDER_TK]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip()


def open_path(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)
        return
    subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def reveal(file: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(file)])
        return
    if sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{file}"])
        return
    open_path(file.parent)
