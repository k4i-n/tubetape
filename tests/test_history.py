from pathlib import Path

from tubetape.history import History


def test_add_puts_newest_first_and_replaces_same_file(tmp_path: Path) -> None:
    history = History(tmp_path / "h.json")
    history.add("a", "ua", "A", "/m/a.mp3", "mp3")
    history.add("b", "ub", "B", "/m/b.mp3", "mp3")
    history.add("a", "ua", "A2", "/m/a.mp3", "mp3")
    assert [e["title"] for e in history.entries()] == ["A2", "B"]


def test_persists_across_instances(tmp_path: Path) -> None:
    History(tmp_path / "h.json").add("a", "ua", "A", "/m/a.mp3", "mp3")
    assert [e["id"] for e in History(tmp_path / "h.json").entries()] == ["a"]


def test_remove_and_clear_bump_version(tmp_path: Path) -> None:
    history = History(tmp_path / "h.json")
    history.add("a", "ua", "A", "/m/a.mp3", "mp3")
    history.add("b", "ub", "B", "/m/b.mp3", "mp3")
    history.remove("/m/a.mp3")
    assert [e["id"] for e in history.entries()] == ["b"]
    assert history.has_file("/m/b.mp3") and not history.has_file("/m/a.mp3")
    before = history.version
    history.clear()
    assert history.entries() == [] and history.version == before + 1


def test_corrupt_file_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "h.json"
    path.write_text("{not json")
    assert History(path).entries() == []
