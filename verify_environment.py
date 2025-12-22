#!/usr/bin/env python3
"""
Simple environment verification script.

Checks for `ffmpeg`, `ffprobe`, and `yt-dlp` (binary or Python package), and optionally
prints ffprobe stream info for a provided sample file.
"""

import shutil
import subprocess
import sys
from pathlib import Path
import json


def check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def ffprobe_info(path: Path) -> None:
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        print('ffprobe format info:', json.dumps(data.get('format', {}), indent=2))
    except Exception as e:
        print('ffprobe failed:', e)


def main():
    print('Checking environment...')
    ffmpeg_ok = check_tool('ffmpeg')
    ffprobe_ok = check_tool('ffprobe')
    ytdlp_ok = check_tool('yt-dlp')

    print('ffmpeg on PATH:', ffmpeg_ok)
    print('ffprobe on PATH:', ffprobe_ok)
    print('yt-dlp (binary) on PATH:', ytdlp_ok)

    try:
        import yt_dlp  # type: ignore
        print('yt_dlp Python package: available')
    except Exception:
        print('yt_dlp Python package: not installed')

    if len(sys.argv) > 1:
        sample = Path(sys.argv[1])
        if sample.exists():
            print('Running ffprobe on sample file:', sample)
            ffprobe_info(sample)
        else:
            print('Sample file not found:', sample)


if __name__ == '__main__':
    main()
