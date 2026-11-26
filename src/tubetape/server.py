import json
import re
from collections.abc import Callable
from email.message import Message
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tubetape import desktop
from tubetape.download import Settings, details, playlist, search
from tubetape.history import History
from tubetape.jobs import Item, JobStore
from tubetape.preview import Previews, read

DEFAULT_DEST = Path.home() / "Music" / "tubetape"
SEARCH_PAGE = 20


class App:
    def __init__(self, store: JobStore, history: History, previews: Previews) -> None:
        self.store = store
        self.history = history
        self.previews = previews

    def state(self, query: dict[str, str]) -> Any:
        return {
            "jobs": self.store.snapshot(),
            "historyVersion": self.history.version,
            "defaultDest": str(DEFAULT_DEST),
        }

    def get_history(self, query: dict[str, str]) -> Any:
        return {"entries": self.history.entries()}

    def search(self, query: dict[str, str]) -> Any:
        text = query.get("q", "").strip()
        offset = max(0, int(query.get("offset") or 0))
        kind = query.get("kind", "video")
        results = search(text, offset, SEARCH_PAGE, kind) if text else []
        return {"results": [asdict(r) for r in results], "pageSize": SEARCH_PAGE}

    def playlist(self, query: dict[str, str]) -> Any:
        found = playlist(query.get("url", ""))
        return {"title": found.title, "results": [asdict(r) for r in found.entries]}

    def details(self, query: dict[str, str]) -> Any:
        return asdict(details(query.get("url", "")))

    def preview(self, query: dict[str, str]) -> Any:
        return {"stream": "/api/audio/" + self.previews.start(query.get("url", ""))}

    def start(self, body: dict[str, Any]) -> Any:
        items = [Item(str(i.get("url", "")), str(i.get("title", ""))) for i in body.get("items", [])]
        dest = Path(str(body.get("dest") or DEFAULT_DEST)).expanduser()
        settings = Settings.parse(str(body.get("format", "")), str(body.get("quality", "")))
        self.store.start(items, dest, settings, int(body.get("workers") or 4))
        return {"ok": True}

    def retry(self, body: dict[str, Any]) -> Any:
        self.store.retry(str(body.get("id", "")))
        return {"ok": True}

    def dismiss(self, body: dict[str, Any]) -> Any:
        self.store.dismiss(str(body.get("id", "")))
        return {"ok": True}

    def clear_history(self, body: dict[str, Any]) -> Any:
        self.history.clear()
        self.store.clear_finished()
        return {"ok": True}

    def remove_history(self, body: dict[str, Any]) -> Any:
        self.history.remove(str(body.get("file", "")))
        return {"ok": True}

    def reveal(self, body: dict[str, Any]) -> Any:
        file = str(body.get("file", ""))
        if not self.history.has_file(file) or not Path(file).exists():
            return {"ok": False}
        desktop.reveal(Path(file))
        return {"ok": True}

    def open_folder(self, body: dict[str, Any]) -> Any:
        folder = Path(str(body.get("path") or DEFAULT_DEST)).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        desktop.open_path(folder)
        return {"ok": True}

    def pick_folder(self, body: dict[str, Any]) -> Any:
        return {"path": desktop.pick_folder()}


def is_own_request(headers: Message, port: int, post: bool) -> bool:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if headers.get("Host") not in hosts:
        return False
    if headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return False
    return not post or headers.get("Origin") in {f"http://{host}" for host in hosts}


def make_handler(app: App, port: int) -> type[BaseHTTPRequestHandler]:
    page = files("tubetape").joinpath("index.html").read_bytes()
    gets: dict[str, Callable[[dict[str, str]], Any]] = {
        "/api/state": app.state,
        "/api/history": app.get_history,
        "/api/search": app.search,
        "/api/playlist": app.playlist,
        "/api/preview": app.preview,
        "/api/details": app.details,
    }
    posts: dict[str, Callable[[dict[str, Any]], Any]] = {
        "/api/jobs": app.start,
        "/api/retry": app.retry,
        "/api/dismiss": app.dismiss,
        "/api/history/clear": app.clear_history,
        "/api/history/remove": app.remove_history,
        "/api/reveal": app.reveal,
        "/api/open-folder": app.open_folder,
        "/api/pick-folder": app.pick_folder,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except ConnectionError:
                return

        def _json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(json.dumps(data).encode(), "application/json", status)

        def _call(self, handler: Callable[[Any], Any], arg: Any) -> None:
            try:
                self._json(handler(arg))
            except Exception as e:
                self._json({"error": str(e).removeprefix("ERROR: ")}, HTTPStatus.BAD_GATEWAY)

        def _audio(self, video_id: str) -> None:
            preview = app.previews.get(video_id)
            size = preview.total() if preview else 0
            if preview is None or not size:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            start, end, status = 0, size - 1, HTTPStatus.OK
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if match and (match[1] or match[2]):
                start = int(match[1]) if match[1] else max(0, size - int(match[2]))
                end = min(int(match[2]), size - 1) if match[1] and match[2] else size - 1
                status = HTTPStatus.PARTIAL_CONTENT
            self.send_response(status)
            self.send_header("Content-Type", preview.content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                for chunk in read(preview, start, end - start + 1):
                    self.wfile.write(chunk)
            except ConnectionError:
                return

        def do_GET(self) -> None:
            if not is_own_request(self.headers, port, post=False):
                self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
                return
            url = urlparse(self.path)
            if url.path == "/":
                self._send(page, "text/html; charset=utf-8")
                return
            if url.path.startswith("/api/audio/"):
                self._audio(url.path.removeprefix("/api/audio/"))
                return
            handler = gets.get(url.path)
            if handler is None:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            self._call(handler, query)

        def do_POST(self) -> None:
            if not is_own_request(self.headers, port, post=True):
                self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
                return
            handler = posts.get(urlparse(self.path).path)
            if handler is None:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self._call(handler, body if isinstance(body, dict) else {})

    return Handler


def serve(port: int, history: History, cache: Path) -> ThreadingHTTPServer:
    app = App(JobStore(history), history, Previews(cache))
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port))
