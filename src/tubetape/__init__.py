import argparse
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

from tubetape.download import FORMATS, QUALITIES, Settings, is_playlist, playlist
from tubetape.history import DEFAULT_PATH, History
from tubetape.jobs import MAX_WORKERS, Item, JobStore
from tubetape.server import DEFAULT_DEST, serve


def workers(text: str) -> int:
    n = int(text)
    if not 1 <= n <= MAX_WORKERS:
        raise argparse.ArgumentTypeError(f"{n} is not in 1-{MAX_WORKERS}")
    return n


def read_urls(args: list[str]) -> list[str]:
    urls: list[str] = []
    for arg in args:
        path = Path(arg).expanduser()
        if not path.is_file():
            urls.append(arg)
            continue
        lines = (line.strip() for line in path.read_text().splitlines())
        urls.extend(line for line in lines if line and not line.startswith("#"))
    return urls


def expand(urls: list[str]) -> list[Item]:
    items: list[Item] = []
    for url in urls:
        if not is_playlist(url):
            items.append(Item(url))
            continue
        items.extend(Item(e.url, e.title) for e in playlist(url).entries)
    return items


def get(urls: list[str], dest: Path, settings: Settings, workers: int) -> int:
    store = JobStore(History(DEFAULT_PATH))
    store.start(expand(urls), dest, settings, workers)
    while store.is_busy():
        time.sleep(1)
    jobs = store.snapshot()
    failed = [job for job in jobs if job["status"] == "error"]
    for job in jobs:
        if job["status"] == "error":
            print(f"FAIL  {job['url']}  {job['error']}", file=sys.stderr)
            continue
        print(f"OK    {job['title']}")
    print(f"{len(jobs) - len(failed)} saved to {dest}, {len(failed)} failed")
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="tubetape")
    sub = parser.add_subparsers(dest="command")
    serve_cmd = sub.add_parser("serve", help="browser app (default)")
    serve_cmd.add_argument("--port", type=int, default=8765)
    get_cmd = sub.add_parser("get", help="download URLs or text files of URLs")
    get_cmd.add_argument("sources", nargs="+")
    get_cmd.add_argument("-o", "--dest", type=Path, default=DEFAULT_DEST)
    get_cmd.add_argument("-w", "--workers", type=workers, metavar=f"1-{MAX_WORKERS}", default=4)
    get_cmd.add_argument("-f", "--format", choices=FORMATS, default="mp3")
    get_cmd.add_argument("-q", "--quality", choices=QUALITIES, default="0", help="kbps, 0 = best VBR")
    args = parser.parse_args()

    if args.command == "get":
        settings = Settings.parse(args.format, args.quality)
        sys.exit(get(read_urls(args.sources), args.dest.expanduser(), settings, args.workers))

    port = getattr(args, "port", 8765)
    with tempfile.TemporaryDirectory(prefix="tubetape-") as cache:
        server = serve(port, History(DEFAULT_PATH), Path(cache))
        url = f"http://127.0.0.1:{port}"
        print(f"tubetape on {url}")
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
