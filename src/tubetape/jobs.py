import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from tubetape.download import Progress, Settings, download_audio
from tubetape.history import History

MAX_WORKERS = 32
ACTIVE = ("queued", "starting", "downloading", "converting")


@dataclass(frozen=True)
class Item:
    url: str
    title: str = ""


@dataclass(frozen=True)
class Job:
    id: str
    url: str
    title: str = ""
    status: str = "queued"
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int = 0
    error: str = ""
    file: str = ""


class Limit:
    def __init__(self, limit: int) -> None:
        self._cond = threading.Condition()
        self._limit = limit
        self._running = 0

    def set(self, limit: int) -> None:
        with self._cond:
            self._limit = max(1, min(limit, MAX_WORKERS))
            self._cond.notify_all()

    def __enter__(self) -> None:
        with self._cond:
            self._cond.wait_for(lambda: self._running < self._limit)
            self._running += 1

    def __exit__(self, *_: object) -> None:
        with self._cond:
            self._running -= 1
            self._cond.notify_all()


class JobStore:
    def __init__(self, history: History) -> None:
        self._history = history
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._params: dict[str, tuple[Path, Settings]] = {}
        self._limit = Limit(4)
        self._pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(job) for job in self._jobs.values()]

    def is_busy(self) -> bool:
        with self._lock:
            return any(job.status in ACTIVE for job in self._jobs.values())

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = {k: j for k, j in self._jobs.items() if j.status in ACTIVE}

    def dismiss(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status not in ACTIVE:
                del self._jobs[job_id]

    def start(self, items: list[Item], dest: Path, settings: Settings, workers: int) -> None:
        unique = {item.url.strip(): item for item in items if item.url.strip()}
        jobs = [Job(id=uuid.uuid4().hex, url=url, title=item.title) for url, item in unique.items()]
        with self._lock:
            for job in jobs:
                self._jobs[job.id] = job
                self._params[job.id] = (dest, settings)
        self._limit.set(workers)
        for job in jobs:
            self._pool.submit(self._run, job.id)

    def retry(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "error":
                return
            self._jobs[job_id] = replace(job, status="queued", error="", downloaded=0, total=0)
        self._pool.submit(self._run, job_id)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if not changes.get("title"):
                changes.pop("title", None)
            self._jobs[job_id] = replace(job, **changes)

    def _run(self, job_id: str) -> None:
        with self._lock:
            url = self._jobs[job_id].url
            dest, settings = self._params[job_id]

        def on_progress(p: Progress) -> None:
            self._update(job_id, **asdict(p))

        with self._limit:
            self._update(job_id, status="starting")
            try:
                result = download_audio(url, dest, settings, on_progress)
            except Exception as e:
                self._update(job_id, status="error", error=str(e).removeprefix("ERROR: "))
                return
        self._history.add(result.id, url, result.title, result.file, settings.format)
        self._update(job_id, status="done", title=result.title, file=result.file, speed=0.0, eta=0)
