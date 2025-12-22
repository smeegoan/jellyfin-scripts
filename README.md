# Jellyfin Scripts

A small collection of utility scripts commonly used with Jellyfin media servers. The repository contains cross-platform and PowerShell tools to help with audio normalization and metadata enrichment.

Files in this repository

- [convert_to_ac3.py](convert_to_ac3.py) — Python script that inspects video files and converts or normalizes audio streams to AC3/E-AC3, filters tracks by language, and removes unwanted streams.
- [DownloadTrailers.ps1](DownloadTrailers.ps1) — PowerShell helper to download movie trailers.
 - [download_trailers.py](download_trailers.py) — Python version of the trailer downloader (TMDb lookup + yt-dlp). See usage below.
- [requirements.txt](requirements.txt) — Optional Python dependencies (e.g., python-dotenv).
- [LICENSE](LICENSE) — Project license.

Overview: convert_to_ac3.py

`convert_to_ac3.py` is the primary cross-platform tool in this repo. It uses `ffprobe` to read stream information and `ffmpeg` to perform fast copying or re-encoding of audio streams. The script aims to produce playback-friendly AC3/E-AC3 audio tracks while preserving the video and subtitle streams you choose to keep.

Motivation: "denom", Jellyfin and AAC streams

Some users and deployments experienced problems where Jellyfin would decide to transcode or mishandle certain AAC audio tracks. Those issues are often caused by unreliable or missing stream metadata (for example, bitrates not reported by `ffprobe` or fractional/frame-related fields), differences in how container metadata is interpreted, or limitations in client passthrough support. In a few cases, stream inspector fields that include numerator/denominator values (sometimes seen in `ffprobe` output) contributed to inconsistent analysis by Jellyfin's decision logic.

Rather than rely on varied container/codec metadata and risk unnecessary server transcoding (which increases CPU load and may degrade audio), this script normalizes audio to AC3/E-AC3. AC3 is widely supported for passthrough on many clients and avoids the edge cases that trigger Jellyfin to transcode AAC streams. The converter therefore improves interoperability and reduces unpredictable transcoding caused by ambiguous or missing stream metadata.

Key functionality

- Auto-detects audio and subtitle streams with language, channels, and bitrate information.
- Keeps only desired languages (defaults to English and Portuguese plus unknown/und).
- Chooses the best audio stream by channel count and bitrate.
- Skips processing when a single suitable AC3/E-AC3 track already exists.
- Supports several processing flows: copying a single good stream, converting a single stream to E-AC3, converting lossless audio to AC3/E-AC3, and stripping non-AC3 streams.
- Optional: write outputs to a temporary directory and copy back to the original location.
- Optional: hardware acceleration hints passed to `ffmpeg` (requires compatible `ffmpeg` build).

Requirements

- Python 3.8 or newer (tested with Python 3.11+)
- `ffmpeg` and `ffprobe` available on PATH
- Optional: `python-dotenv` (install with `pip install -r requirements.txt`) to load defaults from a `.env` file

Additional tools and verification

- Install `yt-dlp` to allow trailer downloads. Either install the binary (available on PATH) or the Python package via `pip install yt-dlp`.
- The repository includes `verify_environment.py` to check that `ffmpeg`, `ffprobe` and `yt-dlp` are available and to run a sample `ffprobe` on a file:

```bash
python verify_environment.py /path/to/sample.mkv
```

Add `requests` and `yt-dlp` to your Python environment if you plan to run `download_trailers.py`:

```bash
pip install -r requirements.txt
```

Usage (convert_to_ac3.py)

Basic invocation:

```bash
python convert_to_ac3.py /path/to/videos
```

Options

- `directory` (positional) — Directory containing video files (wildcards: `*.mp4`, `*.mkv`). If omitted, the `CONVERT_DIRECTORY` environment variable can provide a default.
- `--max-parallel` — Maximum parallel jobs (default from env or 3).
- `--temp-directory` — Local temp directory for faster I/O when converting large files.
- `--use-hw-accel` — Enable `ffmpeg` hardware acceleration hints.
- `--hw-accel-type` — One of `auto`, `nvenc`, `qsv`, `amf`.
- `--languages` — Comma-separated languages to keep (e.g., `eng,por,spa`). Always preserves `unknown`/`und` unless otherwise filtered.

Environment variables (optional)

- `CONVERT_DIRECTORY` — Default directory to process.
- `CONVERT_MAX_PARALLEL` — Default maximum parallel jobs.
- `CONVERT_TEMP_DIRECTORY` — Default temp directory to use.
- `CONVERT_USE_HW_ACCEL` — `true`/`false` default for hardware accel.
- `CONVERT_HW_ACCEL_TYPE` — Default hardware accel type.
- `CONVERT_LANGUAGES` — Default comma-separated languages.

Examples

Sequential processing of current directory:

```bash
python convert_to_ac3.py .
```

Process with a temp directory and two parallel jobs (Windows example):

```powershell
python convert_to_ac3.py "C:\Movies" --temp-directory "C:\Temp\conv" --max-parallel 2
```

Keep only English and Spanish tracks:

```bash
python convert_to_ac3.py /media/movies --languages eng,spa
```

Notes and troubleshooting

- Ensure `ffmpeg` and `ffprobe` are installed and available on PATH. If the script fails when calling these tools, fix your PATH or install a build of `ffmpeg` that includes `ffprobe`.
- The script renames the original file to `*_old.ext` and replaces it with the converted file. When using a separate temp directory, converted files are copied back into place and temp files are removed.
- Hardware acceleration flags are advisory; only use them if your `ffmpeg` build supports the chosen accelerator.
- `DownloadTrailers.ps1` is a PowerShell helper for downloading trailers — run it from PowerShell on Windows.

Support and contributions

Issues and pull requests are welcome. If you add features or change behaviour, please update this README to match.

License

See [LICENSE](LICENSE).

Trailer downloader (Python)

This repository now includes `download_trailers.py`, a cross-platform Python implementation of the original PowerShell `DownloadTrailers.ps1`.

Basic usage:

```bash
python download_trailers.py /path/to/movies --api-key YOUR_TMDB_API_KEY
```

The script will search for media files in the directory, attempt to read an NFO for the original title, query TMDb for a trailer, and download the first YouTube trailer using `yt-dlp`.

Options include `--trailer-dir` to place downloads in a different folder and `--dry-run` to only show which trailers would be downloaded.

