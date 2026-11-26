# tubetape

Save YouTube audio as mp3 or m4a on your own computer, without converter sites or ads. A small browser app and a command line, built on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (download) and ffmpeg (conversion, with title, artist and cover art embedded).

Runs on macOS, Windows and Linux.

## Install

Needs [uv](https://docs.astral.sh/uv/), ffmpeg and Node.js (yt-dlp uses Node to run YouTube's player code).

| System | ffmpeg and Node |
|---|---|
| macOS | `brew install ffmpeg node` |
| Windows | `winget install Gyan.FFmpeg OpenJS.NodeJS.LTS` |
| Debian / Ubuntu | `sudo apt install ffmpeg nodejs` |

```sh
uv tool install git+https://github.com/k4i-n/tubetape
```

## Use

```sh
tubetape                                        # browser app on http://127.0.0.1:8765
tubetape get URL [URL ...]                      # download now, to ~/Music/tubetape
tubetape get list.txt -o ~/Music/x -w 8 -f m4a  # one URL per line, lines starting with # skipped
tubetape get URL -q 192                         # mp3 bitrate: 0 (best VBR), 320, 256, 192, 128
tubetape get 'https://www.youtube.com/playlist?list=…'  # one file per video
```

`-w` sets how many download at once, 1 to 32 (default 4).

In the browser app, search videos or playlists, click a result to preview it and + to queue it. Paste links into the queue or anywhere on the page; a playlist link queues every video. Pick the folder, MP3 or M4A, bitrate and how many at once, then Download. Finished files are listed under Downloads; removing them from the list leaves the files on disk.

The app listens only on 127.0.0.1 and answers only its own page. Download history is kept in your user data folder (`~/Library/Application Support/tubetape` on macOS, `%APPDATA%\tubetape` on Windows, `~/.local/share/tubetape` on Linux).

## When downloads fail

YouTube changes often. Upgrade yt-dlp first:

```sh
uv tool upgrade tubetape
```

## Develop

```sh
uv run mypy src tests && uv run pytest
```

## License

MIT. Download only what you have the right to keep, and follow YouTube's terms where you live.
