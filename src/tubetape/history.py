import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tubetape.desktop import data_dir

DEFAULT_PATH = data_dir("tubetape") / "history.json"


@dataclass(frozen=True)
class Entry:
    id: str
    url: str
    title: str
    file: str
    format: str
    at: float


class History:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._entries = self._load()
        self.version = 0

    def _load(self) -> list[Entry]:
        try:
            data = json.loads(self._path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return [Entry(**item) for item in data if isinstance(item, dict)]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(e) for e in self._entries], ensure_ascii=False))
        tmp.replace(self._path)
        self.version += 1

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(e) for e in self._entries]

    def has_file(self, file: str) -> bool:
        with self._lock:
            return any(e.file == file for e in self._entries)

    def add(self, id: str, url: str, title: str, file: str, format: str) -> None:
        entry = Entry(id=id, url=url, title=title, file=file, format=format, at=time.time())
        with self._lock:
            self._entries = [entry, *(e for e in self._entries if e.file != file)]
            self._save()

    def remove(self, file: str) -> None:
        with self._lock:
            self._entries = [e for e in self._entries if e.file != file]
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._entries = []
            self._save()
