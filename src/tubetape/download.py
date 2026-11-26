from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp

ATTEMPTS = 3
FORMATS = ("mp3", "m4a")
QUALITIES = ("0", "320", "256", "192", "128")
UNAVAILABLE = ("[Private video]", "[Deleted video]")
KINDS = ("video", "views", "playlist")
PLAYLIST_FILTER = "EgIQAw%3D%3D"
MOST_VIEWED_FILTER = "CAMSAhAB"


@dataclass(frozen=True)
class Progress:
    status: str
    title: str = ""
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int = 0


OnProgress = Callable[[Progress], None]


@dataclass(frozen=True)
class Settings:
    format: str = "mp3"
    quality: str = "0"

    @classmethod
    def parse(cls, format: str, quality: str) -> "Settings":
        return cls(
            format=format if format in FORMATS else "mp3",
            quality=quality if quality in QUALITIES else "0",
        )


@dataclass(frozen=True)
class Result:
    id: str
    title: str
    file: str


@dataclass(frozen=True)
class SearchResult:
    id: str
    url: str
    title: str
    channel: str
    duration: int
    thumbnail: str
    views: int = 0
    kind: str = "video"


@dataclass(frozen=True)
class Details:
    views: int
    uploaded: str
    subscribers: int


@dataclass(frozen=True)
class Playlist:
    title: str
    entries: list[SearchResult]


class QuietLogger:
    def debug(self, msg: str) -> None:
        return

    def info(self, msg: str) -> None:
        return

    def warning(self, msg: str) -> None:
        return

    def error(self, msg: str) -> None:
        return


QUIET = QuietLogger()


def forbidden(e: Exception) -> bool:
    return "HTTP Error 403" in str(e)


def options(dest: Path, settings: Settings, on_progress: OnProgress) -> dict[str, Any]:
    def download_hook(d: dict[str, Any]) -> None:
        title = str(d.get("info_dict", {}).get("title", ""))
        if d["status"] == "finished":
            on_progress(Progress("converting", title))
            return
        if d["status"] != "downloading":
            return
        on_progress(
            Progress(
                status="downloading",
                title=title,
                downloaded=int(d.get("downloaded_bytes") or 0),
                total=int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0),
                speed=float(d.get("speed") or 0),
                eta=int(d.get("eta") or 0),
            )
        )

    return {
        "format": "bestaudio[ext=m4a]/bestaudio" if settings.format == "m4a" else "bestaudio/best",
        "outtmpl": str(dest / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "writethumbnail": True,
        "js_runtimes": {"node": {}},
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": settings.format,
                "preferredquality": settings.quality,
            },
            {"key": "FFmpegMetadata"},
            {"key": "EmbedThumbnail"},
        ],
        "progress_hooks": [download_hook],
        "logger": QUIET,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }


def download_once(url: str, dest: Path, settings: Settings, on_progress: OnProgress) -> Result:
    with yt_dlp.YoutubeDL(options(dest, settings, on_progress)) as ydl:
        info = ydl.extract_info(url, download=True)
    downloads = info.get("requested_downloads") or [{}]
    return Result(
        id=str(info.get("id") or ""),
        title=str(info.get("title") or ""),
        file=str(downloads[0].get("filepath") or ""),
    )


def download_audio(url: str, dest: Path, settings: Settings, on_progress: OnProgress) -> Result:
    dest.mkdir(parents=True, exist_ok=True)
    for _ in range(ATTEMPTS - 1):
        try:
            return download_once(url, dest, settings, on_progress)
        except yt_dlp.utils.DownloadError as e:
            if not forbidden(e):
                raise
    return download_once(url, dest, settings, on_progress)


def is_playlist(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path == "/playlist" and "list" in parse_qs(parsed.query)


def _playable(e: dict[str, Any]) -> bool:
    return (
        e.get("ie_key") == "Youtube"
        and e.get("live_status") != "is_live"
        and e.get("title") not in UNAVAILABLE
    )


def _result(e: dict[str, Any]) -> SearchResult:
    return SearchResult(
        id=str(e["id"]),
        url=f"https://www.youtube.com/watch?v={e['id']}",
        title=str(e.get("title") or ""),
        channel=str(e.get("channel") or ""),
        duration=int(e.get("duration") or 0),
        thumbnail=str((e.get("thumbnails") or [{}])[0].get("url") or ""),
        views=int(e.get("view_count") or 0),
    )


def _flat(url: str, **extra: Any) -> dict[str, Any]:
    opts = {"extract_flat": "in_playlist", "logger": QUIET, "quiet": True, "no_warnings": True, **extra}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info: dict[str, Any] = ydl.extract_info(url, download=False) or {}
    return info


def _playlist_result(e: dict[str, Any]) -> SearchResult:
    return SearchResult(
        id=str(e["id"]),
        url=f"https://www.youtube.com/playlist?list={e['id']}",
        title=str(e.get("title") or ""),
        channel=str(e.get("channel") or e.get("uploader") or ""),
        duration=0,
        thumbnail=str((e.get("thumbnails") or [{}])[0].get("url") or ""),
        kind="playlist",
    )


def _results_url(query: str, filter: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote(query)}&sp={filter}"


def search(query: str, offset: int, limit: int, kind: str = "video") -> list[SearchResult]:
    pages = {"playliststart": offset + 1, "playlistend": offset + limit}
    if kind == "playlist":
        info = _flat(_results_url(query, PLAYLIST_FILTER), **pages)
        return [
            _playlist_result(e)
            for e in info.get("entries") or []
            if e.get("ie_key") == "YoutubeTab" and is_playlist(str(e.get("url") or ""))
        ]
    if kind == "views":
        info = _flat(_results_url(query, MOST_VIEWED_FILTER), **pages)
        found = [_result(e) for e in info.get("entries") or [] if _playable(e)]
        return sorted(found, key=lambda r: r.views, reverse=True)
    info = _flat(f"ytsearch{offset + limit}:{query}", **pages)
    return [_result(e) for e in info.get("entries") or [] if _playable(e)]


def playlist(url: str) -> Playlist:
    info = _flat(url)
    entries = [_result(e) for e in info.get("entries") or [] if _playable(e)]
    return Playlist(title=str(info.get("title") or ""), entries=entries)


def details(url: str) -> Details:
    opts = {"logger": QUIET, "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info: dict[str, Any] = ydl.extract_info(url, download=False, process=False) or {}
    return Details(
        views=int(info.get("view_count") or 0),
        uploaded=str(info.get("upload_date") or ""),
        subscribers=int(info.get("channel_follower_count") or 0),
    )
