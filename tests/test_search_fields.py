from typing import Any

import pytest

from tubetape import download


class FakeYDL:
    info: dict[str, Any] = {}

    def __init__(self, opts: dict[str, Any]) -> None:
        return

    def __enter__(self) -> "FakeYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return

    def extract_info(self, url: str, download: bool, process: bool = True) -> dict[str, Any]:
        return self.info


def test_result_carries_views() -> None:
    assert download._result({"id": "a", "view_count": 1200}).views == 1200
    assert download._result({"id": "a"}).views == 0


def test_details_reads_views_date_and_subscribers(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeYDL.info = {"view_count": 5, "upload_date": "20091025", "channel_follower_count": 4560000}
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    assert download.details("u") == download.Details(views=5, uploaded="20091025", subscribers=4560000)


def test_details_missing_fields_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeYDL.info = {}
    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYDL)
    assert download.details("u") == download.Details(views=0, uploaded="", subscribers=0)


def test_most_viewed_search_sorts_each_page(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def flat(url: str, **extra: Any) -> dict[str, Any]:
        urls.append(url)
        entries = [{"id": i, "ie_key": "Youtube", "view_count": v} for i, v in (("a", 5), ("b", None), ("c", 9))]
        return {"entries": entries}

    monkeypatch.setattr(download, "_flat", flat)
    assert [r.id for r in download.search("lofi", 0, 20, "views")] == ["c", "a", "b"]
    assert urls == ["https://www.youtube.com/results?search_query=lofi&sp=CAMSAhAB"]
