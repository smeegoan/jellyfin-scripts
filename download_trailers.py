#!/usr/bin/env python3
"""
Download movie trailers using TMDb lookup and yt-dlp.

Replicates the behavior of the original DownloadTrailers.ps1 script:
- Walk a movie directory for media files (*.mp4, *.mkv, *.avi)
- For each movie, try to read an accompanying .nfo and extract movie.originaltitle
- Query TMDb for the movie, fetch its videos, pick the first YouTube trailer
- Download the trailer using `yt-dlp` (invoked as subprocess)

Requirements: requests, yt-dlp available on PATH (or adjust the script to use the yt_dlp Python package)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import shutil
import requests
from urllib.parse import quote_plus

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except Exception:
    YT_DLP_AVAILABLE = False


def sanitize_filename(name: str, replacement: str = "") -> str:
    # Remove characters invalid for filenames on Windows and other OSes
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, replacement)
    return name


def get_movie_name_from_nfo(nfo_path: Path) -> Optional[str]:
    if not nfo_path.exists():
        return None
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        # Look for movie/originaltitle
        orig = root.find('./originaltitle')
        if orig is not None and orig.text:
            return orig.text.strip()
        # Some NFOs use <movie><originaltitle>...
        movie = root.find('./movie')
        if movie is not None:
            orig2 = movie.find('./originaltitle')
            if orig2 is not None and orig2.text:
                return orig2.text.strip()
    except Exception:
        # Parsing errors are non-fatal; fall back to filename
        return None
    return None


def get_movie_trailer_url(movie_name: str, api_key: str) -> Optional[str]:
    search_url = 'https://api.themoviedb.org/3/search/movie'
    try:
        params = {'api_key': api_key, 'query': movie_name}
        r = requests.get(search_url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get('results') or []
        if not results:
            return None
        movie_id = results[0].get('id')
        if not movie_id:
            return None

        videos_url = f'https://api.themoviedb.org/3/movie/{movie_id}/videos'
        r2 = requests.get(videos_url, params={'api_key': api_key}, timeout=15)
        r2.raise_for_status()
        vdata = r2.json()
        vids = vdata.get('results') or []
        # Find first YouTube trailer
        for v in vids:
            if v.get('type') == 'Trailer' and v.get('site') == 'YouTube' and v.get('key'):
                return f'https://www.youtube.com/watch?v={v.get("key")}'
    except Exception:
        return None
    return None


def download_youtube_video(youtube_url: str, output_path: Path, cookies_from_browser: Optional[str], cookies_file: Optional[str]) -> int:
    if not YT_DLP_AVAILABLE:
        # Fallback to external binary
        cmd = ['yt-dlp']
        if cookies_from_browser:
            cmd += ['--cookies-from-browser', cookies_from_browser]
        cmd += ['-f', 'mp4']
        if cookies_file:
            cmd += ['--cookies', str(cookies_file)]
        cmd += ['-o', str(output_path), youtube_url, '--sub-langs', 'pt.*']
        print('Running external yt-dlp:', ' '.join(cmd))
        proc = subprocess.run(cmd)
        return proc.returncode

    ydl_opts = {
        'format': 'mp4',
        'outtmpl': str(output_path),
        'writesubtitles': True,
        'subtitleslangs': ['pt.*'],
        'cookiesfrombrowser': cookies_from_browser if cookies_from_browser else None,
    }
    if cookies_file:
        ydl_opts['cachedir'] = False
        ydl_opts['cookiefile'] = str(cookies_file)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
        return 0
    except Exception as e:
        print('yt_dlp error:', e)
        return 1


def find_movie_files(directory: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pat in patterns:
        files.extend(directory.rglob(pat))
    # Deduplicate while preserving order
    seen = set()
    uniq: list[Path] = []
    for p in files:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def main():
    parser = argparse.ArgumentParser(description='Download movie trailers using TMDb and yt-dlp')
    parser.add_argument('directory', nargs='?', default=os.getenv('TRAILER_MOVIES_DIR'), help='Directory containing movie files')
    parser.add_argument('--trailer-dir', default=os.getenv('TRAILER_OUTPUT_DIR', ''), help='Directory to save downloaded trailers')
    parser.add_argument('--api-key', default=os.getenv('TMDB_API_KEY'), help='TMDb API key (or set TMDB_API_KEY env var)')
    parser.add_argument('--cookies-browser', default='firefox', help='Browser name for --cookies-from-browser (yt-dlp)')
    parser.add_argument('--cookies-file', default='cookies.txt', help='Cookies file passed to yt-dlp (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Do not download, only show found trailers')
    parser.add_argument('--patterns', default='*.mp4,*.mkv,*.avi', help='Comma-separated glob patterns')
    args = parser.parse_args()

    if not args.directory:
        parser.error('directory is required (positional argument or TRAILER_MOVIES_DIR env var)')

    movie_dir = Path(args.directory)
    if not movie_dir.exists():
        print('Directory does not exist:', movie_dir)
        sys.exit(1)

    trailer_dir = Path(args.trailer_dir) if args.trailer_dir else (movie_dir / 'Trailers')
    trailer_dir.mkdir(parents=True, exist_ok=True)

    api_key = args.api_key
    if not api_key:
        print('TMDb API key is required; set --api-key or TMDB_API_KEY environment variable')
        sys.exit(1)

    yt_dlp_path = shutil.which('yt-dlp')
    if not yt_dlp_path:
        print('Warning: yt-dlp not found on PATH. The script will still attempt to call yt-dlp, but this may fail.')

    patterns = [p.strip() for p in args.patterns.split(',') if p.strip()]
    movie_files = find_movie_files(movie_dir, patterns)
    print(f'Found {len(movie_files)} media files')

    for movie in movie_files:
        nfo_path = movie.with_suffix('.nfo')
        movie_name = get_movie_name_from_nfo(nfo_path) or movie.stem

        print(f'Processing: {movie_name} ({movie})')
        trailer_url = get_movie_trailer_url(movie_name, api_key)
        if not trailer_url:
            print(f'  No trailer found for "{movie_name}"')
            continue

        print(f'  Found trailer: {trailer_url}')
        output_file = trailer_dir / f"{sanitize_filename(movie_name)}.mp4"

        if args.dry_run:
            print(f'  Dry run: would download to {output_file}')
            continue

        ret = download_youtube_video(trailer_url, output_file, args.cookies_browser, args.cookies_file)
        if ret == 0:
            print(f'  Trailer downloaded to: {output_file}')
        else:
            print(f'  yt-dlp failed with exit code {ret} for {movie_name}')


if __name__ == '__main__':
    main()
