import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import yt_dlp

from tubetape.download import ATTEMPTS, QUIET, forbidden

log = logging.getLogger("tubetape")

CHUNK = 64 * 1024
WAIT = 0.1
TIMEOUT = 60.0
TYPES = {".m4a": "audio/mp4", ".webm": "audio/webm"}


@dataclass
class Preview:
    path: Path
    size: int
    done: threading.Event = field(default_factory=threading.Event)
    failed: bool = False

    @property
    def part(self) -> Path:
        return self.path.with_name(self.path.name + ".part")

    @property
    def content_type(self) -> str:
        return TYPES.get(self.path.suffix, "application/octet-stream")

    def total(self) -> int:
        if self.size:
            return self.size
        self.done.wait(TIMEOUT)
        return self.path.stat().st_size if self.path.is_file() else 0


class Previews:
    def __init__(self, cache: Path) -> None:
        self._cache = cache
        self._lock = threading.Lock()
        self._items: dict[str, Preview] = {}

    def get(self, video_id: str) -> Preview | None:
        with self._lock:
            return self._items.get(video_id)

    def start(self, url: str) -> str:
        ydl = yt_dlp.YoutubeDL(
            {
                "format": "bestaudio[ext=m4a]/bestaudio",
                "outtmpl": str(self._cache / "%(id)s.%(ext)s"),
                "noplaylist": True,
                "js_runtimes": {"node": {}},
                "logger": QUIET,
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
            }
        )
        info = ydl.extract_info(url, download=False)
        video_id = str(info["id"])
        with self._lock:
            existing = self._items.get(video_id)
            if existing and not existing.failed:
                ydl.close()
                return video_id
            preview = Preview(Path(ydl.prepare_filename(info)), int(info.get("filesize") or 0))
            self._items[video_id] = preview
        threading.Thread(target=self._download, args=(ydl, url, info, preview), daemon=True).start()
        return video_id

    def _download(self, ydl: Any, url: str, info: dict[str, Any], preview: Preview) -> None:
        try:
            for _ in range(ATTEMPTS - 1):
                try:
                    ydl.process_info(info)
                    return
                except yt_dlp.utils.DownloadError as e:
                    if not forbidden(e):
                        raise
                    info = ydl.extract_info(url, download=False)
            ydl.process_info(info)
        except Exception as e:
            preview.failed = True
            log.warning("preview failed: %s: %s", url, e)
        finally:
            preview.done.set()
            ydl.close()


def _open(preview: Preview) -> IO[bytes] | None:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        for path in (preview.path, preview.part):
            try:
                return path.open("rb")
            except FileNotFoundError:
                continue
        if preview.done.is_set():
            return None
        time.sleep(WAIT)
    return None


def read(preview: Preview, start: int, length: int) -> Iterator[bytes]:
    f = _open(preview)
    if f is None:
        return
    with f:
        f.seek(start)
        remaining = length
        deadline = time.monotonic() + TIMEOUT
        while remaining > 0 and time.monotonic() < deadline:
            chunk = f.read(min(CHUNK, remaining))
            if chunk:
                remaining -= len(chunk)
                deadline = time.monotonic() + TIMEOUT
                yield chunk
                continue
            if preview.done.is_set():
                return
            time.sleep(WAIT)
