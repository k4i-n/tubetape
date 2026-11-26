from pathlib import Path

import pytest
import yt_dlp

from tubetape import download
from tubetape.download import Progress, Result, Settings

FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
RESULT = Result(id="id", title="title", file="/x/title.mp3")


def fake_once(errors: list[str]) -> tuple[list[int], object]:
    calls: list[int] = []

    def once(url: str, dest: Path, settings: Settings, on_progress: object) -> Result:
        calls.append(1)
        if len(calls) <= len(errors):
            raise yt_dlp.utils.DownloadError(errors[len(calls) - 1])
        return RESULT

    return calls, once


def ignore(p: Progress) -> None:
    return


def test_retries_forbidden_then_succeeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls, once = fake_once([FORBIDDEN, FORBIDDEN])
    monkeypatch.setattr(download, "download_once", once)
    assert download.download_audio("u", tmp_path, Settings(), ignore) == RESULT
    assert len(calls) == 3


def test_gives_up_after_attempts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls, once = fake_once([FORBIDDEN] * 3)
    monkeypatch.setattr(download, "download_once", once)
    with pytest.raises(yt_dlp.utils.DownloadError):
        download.download_audio("u", tmp_path, Settings(), ignore)
    assert len(calls) == download.ATTEMPTS


def test_other_errors_fail_at_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls, once = fake_once(["ERROR: [youtube] x: Video unavailable"])
    monkeypatch.setattr(download, "download_once", once)
    with pytest.raises(yt_dlp.utils.DownloadError):
        download.download_audio("u", tmp_path, Settings(), ignore)
    assert len(calls) == 1


def test_settings_fall_back_to_defaults() -> None:
    assert Settings.parse("wav", "999") == Settings("mp3", "0")
    assert Settings.parse("m4a", "192") == Settings("m4a", "192")
