#!/usr/bin/env python3
"""
Video Audio Stream Converter
Converts audio streams to AC3, filters by language, and removes unwanted tracks.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


class VideoProcessor:
    def __init__(self, temp_dir: Optional[str] = None, use_hw_accel: bool = False, 
                 hw_accel_type: str = "auto", languages: Optional[List[str]] = None):
        self.temp_dir = temp_dir
        self.use_hw_accel = use_hw_accel
        self.hw_accel_type = hw_accel_type
        # Default to English, Portuguese, and unknown/undefined if not specified
        if languages is None:
            languages = ['eng', 'en', 'por', 'pt', 'english', 'portuguese', 'unknown', 'und']
        self.desired_languages = {lang.lower() for lang in languages}
    
    def is_commentary_track(self, stream: Dict) -> bool:
        """Check if an audio stream is a commentary track based on its title."""
        title = stream.get('title', '').lower()
        return 'commentary' in title or 'comentário' in title or 'comentario' in title or 'director' in title
        
    def get_stream_info(self, file_path: Path) -> Tuple[List[Dict], List[Dict], float, float]:
        """Get audio and subtitle stream information using ffprobe."""
        # Get audio streams with bitrate and channel info
        audio_cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=index,codec_name,bit_rate,channels:stream_tags=language,title',
            '-of', 'json',
            str(file_path)
        ]
        
        audio_result = subprocess.run(audio_cmd, capture_output=True, encoding='utf-8', errors='replace')
        audio_text = audio_result.stdout or ''
        try:
            audio_data = json.loads(audio_text)
        except Exception:
            print(f"Warning: failed to parse ffprobe audio output for {file_path.name}; output (truncated):\n{audio_text[:1024]}")
            audio_data = {}
        audio_streams = []
        
        for stream in audio_data.get('streams', []):
            lang = stream.get('tags', {}).get('language', 'unknown').lower()
            if not lang or lang == 'und':
                lang = 'unknown'
            
            # Get title/description
            title = stream.get('tags', {}).get('title', '').lower()
            
            # Get bitrate (may not always be available)
            bitrate = stream.get('bit_rate')
            bitrate_kbps = int(bitrate) // 1000 if bitrate else 0
            
            # Get channel count
            channels = stream.get('channels', 0)
            
            audio_streams.append({
                'index': stream['index'],
                'codec': stream['codec_name'].lower(),
                'language': lang,
                'title': title,
                'bitrate': bitrate_kbps,
                'channels': channels
            })
        
        # Get subtitle streams
        sub_cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 's',
            '-show_entries', 'stream=index,codec_name:stream_tags=language',
            '-of', 'json',
            str(file_path)
        ]
        
        sub_result = subprocess.run(sub_cmd, capture_output=True, encoding='utf-8', errors='replace')
        sub_text = sub_result.stdout or ''
        try:
            sub_data = json.loads(sub_text)
        except Exception:
            print(f"Warning: failed to parse ffprobe subtitle output for {file_path.name}; output (truncated):\n{sub_text[:1024]}")
            sub_data = {}
        subtitle_streams = []
        
        for stream in sub_data.get('streams', []):
            lang = stream.get('tags', {}).get('language', 'unknown').lower()
            if not lang or lang == 'und':
                lang = 'unknown'
            subtitle_streams.append({
                'index': stream['index'],
                'language': lang
            })
        
        # Get duration and fps
        format_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            str(file_path)
        ]
        
        format_result = subprocess.run(format_cmd, capture_output=True, encoding='utf-8', errors='replace')
        format_text = format_result.stdout or ''
        try:
            format_data = json.loads(format_text)
        except Exception:
            print(f"Warning: failed to parse ffprobe format output for {file_path.name}; output (truncated):\n{format_text[:1024]}")
            format_data = {}
        duration = float(format_data.get('format', {}).get('duration', 0) or 0)
        
        # Get FPS
        fps_cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'json',
            str(file_path)
        ]
        
        fps_result = subprocess.run(fps_cmd, capture_output=True, encoding='utf-8', errors='replace')
        fps_text = fps_result.stdout or ''
        try:
            fps_data = json.loads(fps_text)
        except Exception:
            print(f"Warning: failed to parse ffprobe fps output for {file_path.name}; output (truncated):\n{fps_text[:1024]}")
            fps_data = {}
        fps_str = fps_data.get('streams', [{}])[0].get('r_frame_rate', '24/1')
        
        # Parse fps (e.g., "24000/1001" or "24")
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = float(num) / float(den)
        else:
            fps = float(fps_str) if fps_str else 24.0
        
        return audio_streams, subtitle_streams, duration, fps
    
    def filter_streams_by_language(self, streams: List[Dict]) -> List[Dict]:
        """Filter streams to keep only desired languages."""
        return [s for s in streams if s['language'] in self.desired_languages]
    
    def process_file(self, file_path: Path) -> bool:
        """Process a single video file."""
        print(f"\nChecking: {file_path.name}")
        
        try:
            # Get stream information
            audio_streams, subtitle_streams, duration, fps = self.get_stream_info(file_path)
            
            if not audio_streams:
                print(f"Skipping: {file_path.name} (no audio streams found)")
                return False
            
            # Display detected streams
            for stream in audio_streams:
                bitrate_str = f"{stream['bitrate']}kbps" if stream['bitrate'] > 0 else "unknown"
                channel_str = f"{stream['channels']}ch" if stream['channels'] > 0 else "unknown"
                title_str = f", Title: {stream['title']}" if stream['title'] else ""
                print(f"Parsed Audio Stream: Index {stream['index']}, "
                      f"Codec {stream['codec']}, Language {stream['language']}, "
                      f"Bitrate {bitrate_str}, Channels {channel_str}{title_str}")
            
            for stream in subtitle_streams:
                print(f"Parsed Subtitle Stream: Index {stream['index']}, "
                      f"Language {stream['language']}")
            
            # Filter by language
            # Check if we have any audio in our desired languages (excluding unknown/undefined)
            known_desired_langs = self.desired_languages - {'unknown', 'und'}
            has_known_desired_lang = any(s['language'] in known_desired_langs for s in audio_streams)
            
            original_audio_count = len(audio_streams)
            original_sub_count = len(subtitle_streams)
            
            # Only filter audio if we have tracks in our desired languages
            # This prevents removing all audio when no English/Portuguese exists
            # Also skip commentary tracks (keep them regardless of language)
            if has_known_desired_lang:
                filtered_audio = []
                for s in audio_streams:
                    # Keep if: in desired language OR is commentary
                    if s['language'] in self.desired_languages or self.is_commentary_track(s):
                        filtered_audio.append(s)
                        if self.is_commentary_track(s):
                            print(f"Keeping commentary track: Index {s['index']}")
                audio_streams = filtered_audio
            
            subtitle_streams = self.filter_streams_by_language(subtitle_streams)
            
            needs_language_filtering = (len(audio_streams) < original_audio_count or 
                                       len(subtitle_streams) < original_sub_count)
            
            if len(audio_streams) < original_audio_count:
                print(f"Filtering audio: Keeping only English/Portuguese tracks "
                      f"({len(audio_streams)} of {original_audio_count})")
            
            if len(subtitle_streams) < original_sub_count:
                print(f"Filtering subtitles: Keeping only English/Portuguese tracks "
                      f"({len(subtitle_streams)} of {original_sub_count})")
            
            # Find the single best audio stream by channel count, then bitrate.
            # Exclude commentary tracks from selection (they should be kept but not selected as primary)
            if not audio_streams:
                print(f"Skipping: {file_path.name} (no audio streams after language filtering)")
                return False

            # Filter out commentary tracks for selection purposes
            non_commentary = [s for s in audio_streams if not self.is_commentary_track(s)]
            
            if not non_commentary:
                print(f"Skipping: {file_path.name} (only commentary tracks found)")
                return False

            # Prefer existing AC3/E-AC3 streams over lossless formats that need conversion
            # This avoids unnecessary conversion and potential quality loss
            ac3_streams = [s for s in non_commentary if s['codec'] in ('ac3', 'eac3')]
            
            if ac3_streams:
                # Select best AC3/E-AC3 stream by channels, then bitrate
                best_stream = max(ac3_streams, key=lambda s: (s['channels'], s['bitrate']))
                print(f"Found existing AC3/E-AC3 stream - will use instead of converting")
            else:
                # No AC3/E-AC3 available, select stream with most channels for conversion
                best_stream = max(non_commentary, key=lambda s: (s['channels'], s['bitrate']))
            
            print(f"\nBest audio stream: Index {best_stream['index']}, "
                  f"Codec {best_stream['codec']}, {best_stream['channels']}ch, "
                  f"{best_stream['bitrate']}kbps")
            
            # Determine appropriate bitrate for this channel count
            channels = best_stream['channels']
            if channels >= 7:
                target_bitrate = 1536
                target_desc = "E-AC3 7.1+"
            elif channels >= 6:
                target_bitrate = 768
                target_desc = "E-AC3 5.1"
            elif channels >= 3:
                target_bitrate = 640
                target_desc = "E-AC3/AC3"
            else:
                target_bitrate = 448
                target_desc = "E-AC3/AC3 stereo"
            
            # Check if current stream is already AC3/E-AC3 (both are supported, keep as-is)
            is_already_good = best_stream['codec'] in ('ac3', 'eac3')
            
            # Check if ALL audio streams are already AC3/E-AC3 (main + commentary)
            all_ac3 = all(s['codec'] in ('ac3', 'eac3') for s in audio_streams)
            
            # Determine if we need to process
            needs_processing = (
                needs_language_filtering or  # Language filtering needed
                not is_already_good or  # Main stream needs conversion
                (len(audio_streams) > 1 and not all_ac3)  # Multiple streams but not all AC3/E-AC3
            )
            
            if not needs_processing:
                print(f"Skipping: {file_path.name} (already optimal - AC3/E-AC3 audio with correct languages)")
                return False
            
            # Process: either copy best stream or convert to E-AC3
            if is_already_good:
                # Best stream is already good AC3/E-AC3, just strip others
                # But keep commentary tracks!
                commentary_tracks = [s for s in audio_streams if self.is_commentary_track(s)]
                streams_to_keep = [best_stream] + commentary_tracks
                
                return self._process_keep_single_stream(file_path, streams_to_keep,
                                                       subtitle_streams, duration, fps)
            else:
                # Convert best stream to E-AC3 at appropriate bitrate
                # Keep commentary tracks as-is
                commentary_tracks = [s for s in audio_streams if self.is_commentary_track(s)]
                
                return self._process_convert_single_to_eac3(file_path, best_stream, commentary_tracks,
                                                           subtitle_streams, duration, fps)
        
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")
            return False
    
    def _build_ffmpeg_command(self, input_file: Path, output_file: Path,
                             audio_streams: List[Dict], subtitle_streams: List[Dict],
                             audio_codec: str = 'copy') -> List[str]:
        """Build ffmpeg command with proper stream mapping."""
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
        
        # Add hardware acceleration if enabled
        if self.use_hw_accel:
            if self.hw_accel_type == 'nvenc' or self.hw_accel_type == 'auto':
                cmd.extend(['-hwaccel', 'cuda'])
            elif self.hw_accel_type == 'qsv':
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.hw_accel_type == 'amf':
                cmd.extend(['-hwaccel', 'd3d11va'])
        
        cmd.extend(['-i', str(input_file)])
        
        # Map video - use 0:v:0 to be explicit about first video stream
        cmd.extend(['-map', '0:v:0'])
        
        # Map audio streams
        for stream in audio_streams:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Map subtitle streams
        for stream in subtitle_streams:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Set codecs
        cmd.extend(['-c:v', 'copy'])
        
        if audio_codec == 'ac3':
            cmd.extend(['-c:a', 'ac3', '-b:a', '640k', '-threads', '0'])
        else:
            cmd.extend(['-c:a', 'copy'])
        
        cmd.extend(['-c:s', 'copy'])
        
        # Preserve all metadata including HDR
        cmd.extend(['-map_metadata', '0'])
        cmd.extend(['-movflags', 'use_metadata_tags'])
        
        cmd.append(str(output_file))
        
        return cmd
    
    def _run_ffmpeg_with_progress(self, cmd: List[str], duration: float, fps: float,
                                  file_name: str, is_encoding: bool = False, 
                                  audio_bitrate: int = 0) -> bool:
        """Run ffmpeg and show progress."""
        # Create progress file
        progress_fd, progress_file = tempfile.mkstemp(suffix='.txt')
        os.close(progress_fd)
        
        try:
            # Get input and output file paths from command
            input_file = Path(cmd[cmd.index('-i') + 1])
            output_file = Path(cmd[-1])
            
            # Calculate expected output size
            expected_size = 0
            use_size_progress = False
            
            if is_encoding and audio_bitrate > 0:
                # Encoding: estimate based on video + audio bitrate
                video_cmd = [
                    'ffprobe', '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=bit_rate',
                    '-of', 'json',
                    str(input_file)
                ]
                video_result = subprocess.run(video_cmd, capture_output=True, encoding='utf-8', errors='replace')
                video_text = video_result.stdout or ''
                try:
                    video_data = json.loads(video_text)
                except Exception:
                    print(f"Warning: failed to parse ffprobe video bitrate output for {file_name}; output (truncated):\n{video_text[:1024]}")
                    video_data = {}
                video_bitrate = video_data.get('streams', [{}])[0].get('bit_rate')
                
                if video_bitrate:
                    video_size = (int(video_bitrate) * duration) / 8  # bytes
                else:
                    video_size = input_file.stat().st_size * 0.95  # Assume video is 95% of file
                
                audio_size = (audio_bitrate * 1000 * duration) / 8  # Convert kbps to bytes
                expected_size = int((video_size + audio_size) * 1.05)
                use_size_progress = True
            else:
                # Copying: use input file size as baseline (may be smaller if removing streams)
                input_size = input_file.stat().st_size
                # Assume output will be 80-100% of input (since we're removing streams)
                expected_size = int(input_size * 0.9)
                use_size_progress = True
            
            # Insert progress reporting
            cmd_with_progress = cmd[:cmd.index(str(cmd[-1]))]
            cmd_with_progress.extend(['-progress', progress_file])
            cmd_with_progress.append(cmd[-1])
            
            # Start ffmpeg
            # Use text mode for pipes so we receive str and avoid manual decoding
            process = subprocess.Popen(cmd_with_progress, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            
            start_time = time.time()
            last_update = 0
            last_size = 0
            last_size_time = start_time
            
            print(f"Progress: 0.0% - Starting...", end='', flush=True)
            
            # Monitor progress
            while process.poll() is None:
                time.sleep(0.5)
                
                percent = 0
                current_time = 0
                speed_str = "..."
                
                # Size-based progress (works for both copy and encode)
                if use_size_progress and output_file.exists():
                    current_size = output_file.stat().st_size
                    
                    if expected_size > 0:
                        percent = min(99, (current_size / expected_size) * 100)
                    
                    elapsed = time.time() - start_time
                    
                    # Calculate transfer speed in MB/s
                    if elapsed > 0.5:
                        size_diff = current_size - last_size
                        time_diff = time.time() - last_size_time
                        
                        if time_diff > 0:
                            mb_per_sec = (size_diff / (1024 * 1024)) / time_diff
                            speed_str = f"{mb_per_sec:.1f} MB/s"
                            last_size = current_size
                            last_size_time = time.time()
                    
                    # Try to get time for encoding speed
                    if is_encoding and os.path.exists(progress_file):
                        try:
                            with open(progress_file, 'r') as f:
                                content = f.read()
                            match = re.search(r'out_time_us=(\d+)', content)
                            if match:
                                current_time = int(match.group(1)) / 1000000.0
                                if current_time > 0 and elapsed > 0:
                                    encode_speed = current_time / elapsed
                                    speed_str = f"{encode_speed:.2f}x"
                        except:
                            pass
                
                if percent > 0.1:
                    elapsed = time.time() - start_time
                    
                    if elapsed > 0 and percent > 0:
                        total_est = (elapsed / percent) * 100
                        remaining = total_est - elapsed
                        eta_hours = int(remaining // 3600)
                        eta_mins = int((remaining % 3600) // 60)
                        eta_secs = int(remaining % 60)
                        eta_str = f"{eta_hours:02d}:{eta_mins:02d}:{eta_secs:02d}"
                    else:
                        eta_str = "Calculating..."
                    
                    if time.time() - last_update >= 0.5:
                        print(f"\rProgress: {percent:.1f}% - ETA: {eta_str} - Speed: {speed_str}     ",
                              end='', flush=True)
                        last_update = time.time()
            
            # Wait for completion
            stdout_data, stderr_data = process.communicate()
            
            # Check if successful
            if process.returncode == 0:
                print(f"\rProgress: 100% - Complete!                                    ", flush=True)
                print()  # New line after completion
                
                # Verify output file exists and has content
                if not output_file.exists():
                    print(f"ERROR: Output file was not created: {output_file}")
                    return False
                
                output_size = output_file.stat().st_size
                if output_size == 0:
                    print(f"ERROR: Output file is empty (0 bytes): {output_file}")
                    return False
                
                return True
            else:
                print(f"\rProgress: FAILED!                                             ")
                print(f"\nffmpeg exited with error code {process.returncode}")
                
                # Display stderr (already text due to Popen text=True)
                if stderr_data:
                    print("\nffmpeg error output:")
                    print(stderr_data)
                
                return False
        
        except Exception as e:
            print(f"\nError during ffmpeg execution: {e}")
            return False
        
        finally:
            # Ensure temp file is cleaned up
            try:
                if os.path.exists(progress_file):
                    time.sleep(0.5)  # Give process time to release file
                    os.remove(progress_file)
            except:
                pass  # Ignore cleanup errors
    
    def _process_keep_single_stream(self, file_path: Path, streams: List[Dict],
                                   subtitle_streams: List[Dict], duration: float, fps: float) -> bool:
        """Keep only the specified streams (main + commentary), strip everything else."""
        stream_desc = f"{len(streams)} stream(s)" if len(streams) > 1 else f"stream {streams[0]['index']}"
        print(f"Processing: {file_path.name} - Keeping {stream_desc}, stripping all others")
        print("(Fast mode: copying stream, no encoding)")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command(file_path, output_file, streams,
                                         subtitle_streams, audio_codec='copy')
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _process_convert_single_to_eac3(self, file_path: Path, stream: Dict, commentary_tracks: List[Dict],
                                       subtitle_streams: List[Dict], duration: float, 
                                       fps: float) -> bool:
        """Convert single stream to E-AC3 at appropriate bitrate based on channels, keep commentary as-is."""
        channels = stream['channels']
        
        # Determine bitrate based on channel count
        # Note: E-AC3 only supports up to 5.1, so 7.1+ will be downmixed to 5.1
        if channels >= 7:
            bitrate = '768k'
            desc = f"E-AC3 5.1 (downmixed from 7.1+) @ {bitrate}"
            target_channels = 6
        elif channels >= 6:
            bitrate = '768k'
            desc = f"E-AC3 5.1 @ {bitrate}"
            target_channels = 6
        elif channels >= 3:
            bitrate = '640k'
            desc = f"E-AC3 @ {bitrate}"
            target_channels = channels
        else:
            bitrate = '448k'
            desc = f"E-AC3 stereo @ {bitrate}"
            target_channels = 2
        
        print(f"Processing: {file_path.name}")
        print(f"  Converting stream {stream['index']}: {stream['codec']} {channels}ch → {desc}")
        
        output_file = self._get_output_path(file_path)
        
        # Build ffmpeg command for E-AC3 conversion
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
        
        # Add hardware acceleration if enabled
        if self.use_hw_accel:
            if self.hw_accel_type == 'nvenc' or self.hw_accel_type == 'auto':
                cmd.extend(['-hwaccel', 'cuda'])
            elif self.hw_accel_type == 'qsv':
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.hw_accel_type == 'amf':
                cmd.extend(['-hwaccel', 'd3d11va'])
        
        cmd.extend(['-i', str(file_path)])
        
        # Map video - use 0:v:0 to be explicit
        cmd.extend(['-map', '0:v:0'])
        
        # Map main audio stream
        cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Map commentary streams
        for commentary in commentary_tracks:
            cmd.extend(['-map', f'0:{commentary["index"]}'])
        
        # Map subtitle streams
        for sub in subtitle_streams:
            cmd.extend(['-map', f'0:{sub["index"]}'])
        
        # Set codecs
        cmd.extend(['-c:v', 'copy'])
        
        # E-AC3 encoding with explicit channel preservation for main stream
        cmd.extend(['-c:a:0', 'eac3', '-b:a:0', bitrate])
        
        # Explicitly set target channel count for main stream (E-AC3 only supports up to 5.1)
        if target_channels == 6:
            # 5.1 layout: FL+FR+FC+LFE+BL+BR
            cmd.extend(['-ac:a:0', '6'])
        elif target_channels == 2:
            # Stereo
            cmd.extend(['-ac:a:0', '2'])
        # For other channel counts, let ffmpeg handle it automatically
        
        # Copy commentary streams as-is
        for i in range(len(commentary_tracks)):
            cmd.extend([f'-c:a:{i+1}', 'copy'])
        
        cmd.extend(['-threads', '0'])
        cmd.extend(['-c:s', 'copy'])
        
        # Preserve all metadata including HDR
        cmd.extend(['-map_metadata', '0'])
        cmd.extend(['-movflags', 'use_metadata_tags'])
        
        cmd.append(str(output_file))
        
        # Extract bitrate value (e.g., '1536k' -> 1536)
        bitrate_kbps = int(bitrate.replace('k', ''))
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name, 
                                          is_encoding=True, audio_bitrate=bitrate_kbps):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _process_keep_ac3_convert_lossless(self, file_path: Path, good_ac3_streams: List[Dict],
                                           lossless_streams: List[Dict], subtitle_streams: List[Dict],
                                           duration: float, fps: float) -> bool:
        """Keep existing good AC3 and convert lossless to E-AC3 7.1 or AC3 5.1."""
        print(f"Processing: {file_path.name}")
        print(f"  - Keeping {len(good_ac3_streams)} good AC3/E-AC3 stream(s)")
        print(f"  - Converting {len(lossless_streams)} lossless stream(s) to E-AC3/AC3")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command_lossless_convert(file_path, output_file, good_ac3_streams,
                                                          lossless_streams, subtitle_streams)
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _process_convert_lossless(self, file_path: Path, lossless_streams: List[Dict],
                                  subtitle_streams: List[Dict], duration: float, fps: float) -> bool:
        """Convert lossless formats to E-AC3 7.1 or AC3 5.1."""
        print(f"Processing: {file_path.name} - Converting {len(lossless_streams)} lossless stream(s) to E-AC3/AC3")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command_lossless_convert(file_path, output_file, [],
                                                          lossless_streams, subtitle_streams)
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _build_ffmpeg_command_lossless_convert(self, input_file: Path, output_file: Path,
                                               copy_streams: List[Dict], convert_streams: List[Dict],
                                               subtitle_streams: List[Dict]) -> List[str]:
        """Build ffmpeg command to copy good AC3 and convert lossless to E-AC3/AC3."""
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
        
        # Add hardware acceleration if enabled
        if self.use_hw_accel:
            if self.hw_accel_type == 'nvenc' or self.hw_accel_type == 'auto':
                cmd.extend(['-hwaccel', 'cuda'])
            elif self.hw_accel_type == 'qsv':
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.hw_accel_type == 'amf':
                cmd.extend(['-hwaccel', 'd3d11va'])
        
        cmd.extend(['-i', str(input_file)])
        
        # Map video - use 0:v:0 to be explicit
        cmd.extend(['-map', '0:v:0'])
        
        # Map all audio streams (copy + convert)
        all_audio = copy_streams + convert_streams
        for stream in all_audio:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Map subtitle streams
        for stream in subtitle_streams:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Set codecs
        cmd.extend(['-c:v', 'copy'])
        
        # Set per-stream audio codecs
        for i, stream in enumerate(all_audio):
            if stream in copy_streams:
                # Copy existing good AC3/E-AC3
                cmd.extend([f'-c:a:{i}', 'copy'])
            else:
                # Convert lossless to E-AC3 or AC3 based on channel count
                channels = stream['channels']
                if channels >= 7:
                    # 7.1 or higher - use E-AC3 at 1536 kbps with explicit channel count
                    cmd.extend([f'-c:a:{i}', 'eac3', f'-b:a:{i}', '1536k', f'-ac:a:{i}', '8'])
                    print(f"  - Stream {stream['index']}: {stream['codec']} {channels}ch → E-AC3 7.1 @ 1536kbps")
                elif channels >= 6:
                    # 5.1 - use E-AC3 at 768 kbps with explicit channel count
                    cmd.extend([f'-c:a:{i}', 'eac3', f'-b:a:{i}', '768k', f'-ac:a:{i}', '6'])
                    print(f"  - Stream {stream['index']}: {stream['codec']} {channels}ch → E-AC3 5.1 @ 768kbps")
                else:
                    # Stereo or less - use AC3 at 640 kbps
                    cmd.extend([f'-c:a:{i}', 'ac3', f'-b:a:{i}', '640k'])
                    print(f"  - Stream {stream['index']}: {stream['codec']} {channels}ch → AC3 @ 640kbps")
        
        cmd.extend(['-threads', '0'])
        cmd.extend(['-c:s', 'copy'])
        
        # Preserve all metadata including HDR
        cmd.extend(['-map_metadata', '0'])
        cmd.extend(['-movflags', 'use_metadata_tags'])
        
        cmd.append(str(output_file))
        
        return cmd
    
    def _process_keep_best_format(self, file_path: Path, keep_streams: List[Dict],
                                  format_name: str, subtitle_streams: List[Dict], 
                                  duration: float, fps: float) -> bool:
        """Keep only the best format streams (DTS or AC3/E-AC3), strip everything else."""
        print(f"Processing: {file_path.name} - Keeping {len(keep_streams)} {format_name} stream(s), stripping all others")
        print("(Fast mode: copying streams, no encoding)")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command(file_path, output_file, keep_streams,
                                         subtitle_streams, audio_codec='copy')
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _build_ffmpeg_command_mixed(self, input_file: Path, output_file: Path,
                                    copy_streams: List[Dict], convert_streams: List[Dict],
                                    subtitle_streams: List[Dict]) -> List[str]:
        """Build ffmpeg command with mixed copy/encode for audio streams."""
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
        
        # Add hardware acceleration if enabled
        if self.use_hw_accel:
            if self.hw_accel_type == 'nvenc' or self.hw_accel_type == 'auto':
                cmd.extend(['-hwaccel', 'cuda'])
            elif self.hw_accel_type == 'qsv':
                cmd.extend(['-hwaccel', 'qsv'])
            elif self.hw_accel_type == 'amf':
                cmd.extend(['-hwaccel', 'd3d11va'])
        
        cmd.extend(['-i', str(input_file)])
        
        # Map video - use 0:v:0 to be explicit
        cmd.extend(['-map', '0:v:0'])
        
        # Map all audio streams (copy + convert)
        all_audio = copy_streams + convert_streams
        for stream in all_audio:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Map subtitle streams
        for stream in subtitle_streams:
            cmd.extend(['-map', f'0:{stream["index"]}'])
        
        # Set codecs
        cmd.extend(['-c:v', 'copy'])
        
        # Set per-stream audio codecs
        for i, stream in enumerate(all_audio):
            if stream in copy_streams:
                cmd.extend([f'-c:a:{i}', 'copy'])
            else:
                cmd.extend([f'-c:a:{i}', 'ac3', f'-b:a:{i}', '640k'])
        
        cmd.extend(['-threads', '0'])
        cmd.extend(['-c:s', 'copy'])
        
        # Preserve all metadata including HDR
        cmd.extend(['-map_metadata', '0'])
        cmd.extend(['-movflags', 'use_metadata_tags'])
        
        cmd.append(str(output_file))
        
        return cmd
    
    def _process_strip_non_ac3(self, file_path: Path, ac3_streams: List[Dict],
                               subtitle_streams: List[Dict], duration: float, fps: float) -> bool:
        """Strip non-AC3 audio, keep AC3 streams."""
        print(f"Processing: {file_path.name} - Stripping non-AC3 audio streams, keeping only AC3/E-AC3")
        print("(Fast mode: copying streams, no encoding)")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command(file_path, output_file, ac3_streams,
                                         subtitle_streams, audio_codec='copy')
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _process_language_filter(self, file_path: Path, audio_streams: List[Dict],
                                 subtitle_streams: List[Dict], duration: float, fps: float) -> bool:
        """Filter by language only (all audio already AC3)."""
        print(f"Processing: {file_path.name} - Removing non-English/Portuguese audio/subtitle tracks")
        print("(Fast mode: copying streams, no encoding)")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command(file_path, output_file, audio_streams,
                                         subtitle_streams, audio_codec='copy')
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _process_convert_to_ac3(self, file_path: Path, audio_streams: List[Dict],
                               subtitle_streams: List[Dict], duration: float, fps: float) -> bool:
        """Convert audio to AC3."""
        print(f"Processing: {file_path.name} - Converting audio streams to AC3")
        
        output_file = self._get_output_path(file_path)
        cmd = self._build_ffmpeg_command(file_path, output_file, audio_streams,
                                         subtitle_streams, audio_codec='ac3')
        
        if self._run_ffmpeg_with_progress(cmd, duration, fps, file_path.name,
                                          is_encoding=True, audio_bitrate=640):
            return self._finalize_output(file_path, output_file)
        return False
    
    def _get_output_path(self, file_path: Path) -> Path:
        """Get output file path (temp directory if specified)."""
        if self.temp_dir:
            return Path(self.temp_dir) / f"{file_path.stem}_converted{file_path.suffix}"
        else:
            return file_path.parent / f"{file_path.stem}_converted{file_path.suffix}"
    
    def _finalize_output(self, original_file: Path, output_file: Path) -> bool:
        """Replace original with converted file."""
        try:
            # Use timestamp for backup to avoid accumulating _old suffixes
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Remove any existing _old suffixes from the stem to prevent accumulation
            stem = original_file.stem
            while stem.endswith('_old'):
                stem = stem[:-4]
            
            backup_file = original_file.parent / f"{stem}_backup_{timestamp}{original_file.suffix}"
            
            # If using temp directory, copy back with progress
            if self.temp_dir and output_file.parent != original_file.parent:
                print("Copying converted file from temp directory to final location...")
                
                # Rename original to backup
                if original_file.exists():
                    original_file.rename(backup_file)
                
                # Copy from temp to final location
                file_size = output_file.stat().st_size
                copied = 0
                last_update = time.time()
                
                with open(output_file, 'rb') as src, open(original_file, 'wb') as dst:
                    while True:
                        chunk = src.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        dst.write(chunk)
                        copied += len(chunk)
                        
                        if time.time() - last_update >= 1:
                            percent = (copied / file_size) * 100
                            mb_copied = copied / (1024 * 1024)
                            mb_total = file_size / (1024 * 1024)
                            print(f"\rCopying: {percent:.1f}% ({mb_copied:.1f} MB / {mb_total:.1f} MB)     ",
                                  end='', flush=True)
                            last_update = time.time()
                
                print(f"\rCopying: 100% - Complete!                                    ")
                
                # Remove temp file
                output_file.unlink()
            else:
                # Simple rename (same directory)
                original_file.rename(backup_file)
                output_file.rename(original_file)
            
            print(f"Successfully processed: {original_file.name}")
            print(f"Backup saved as: {backup_file.name}")
            return True
        
        except Exception as e:
            print(f"Error finalizing output for {original_file.name}: {e}")
            import traceback
            traceback.print_exc()
            # Try to restore backup
            if backup_file.exists() and not original_file.exists():
                try:
                    backup_file.rename(original_file)
                    print("Restored original file from backup")
                except Exception as restore_e:
                    print(f"Failed to restore backup: {restore_e}")
            return False


def process_directory(directory: str, max_parallel: int = 1, temp_dir: Optional[str] = None,
                     use_hw_accel: bool = False, hw_accel_type: str = "auto",
                     languages: Optional[List[str]] = None):
    """Process all video files in directory."""
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"Directory does not exist: {directory}")
        return
    
    # Find all video files
    video_files = []
    for pattern in ('*.mp4', '*.mkv'):
        video_files.extend(dir_path.rglob(pattern))
    
    if not video_files:
        print(f"No video files found in {directory}")
        return
    
    print(f"Found {len(video_files)} video files")
    
    if temp_dir:
        print(f"Using local temp directory: {temp_dir}")
        os.makedirs(temp_dir, exist_ok=True)
    
    if languages:
        print(f"Filtering to languages: {', '.join(languages)}")
    
    processor = VideoProcessor(temp_dir, use_hw_accel, hw_accel_type, languages)
    
    # Process files
    if max_parallel == 1:
        # Sequential processing
        for file_path in video_files:
            processor.process_file(file_path)
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            futures = {executor.submit(processor.process_file, f): f for f in video_files}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error: {e}")


def main():
    # Load environment variables from .env file if available
    if DOTENV_AVAILABLE:
        load_dotenv()
    
    # Get defaults from environment variables
    env_directory = os.getenv('CONVERT_DIRECTORY')
    env_max_parallel = int(os.getenv('CONVERT_MAX_PARALLEL', '3'))
    env_temp_dir = os.getenv('CONVERT_TEMP_DIRECTORY')
    env_use_hw_accel = os.getenv('CONVERT_USE_HW_ACCEL', 'false').lower() in ('true', '1', 'yes')
    env_hw_accel_type = os.getenv('CONVERT_HW_ACCEL_TYPE', 'auto')
    env_languages_str = os.getenv('CONVERT_LANGUAGES')
    env_languages = [lang.strip() for lang in env_languages_str.split(',')] if env_languages_str else None
    
    parser = argparse.ArgumentParser(
        description='Convert video audio streams to AC3 and filter by language'
    )
    parser.add_argument('directory', nargs='?', default=env_directory,
                       help='Directory containing video files')
    parser.add_argument('--max-parallel', type=int, default=env_max_parallel,
                       help=f'Maximum number of parallel jobs (default: {env_max_parallel})')
    parser.add_argument('--temp-directory', type=str, default=env_temp_dir,
                       help='Local temp directory for faster processing')
    parser.add_argument('--use-hw-accel', action='store_true', default=env_use_hw_accel,
                       help='Use hardware acceleration')
    parser.add_argument('--hw-accel-type', type=str, default=env_hw_accel_type,
                       choices=['auto', 'nvenc', 'qsv', 'amf'],
                       help=f'Hardware acceleration type (default: {env_hw_accel_type})')
    parser.add_argument('--languages', type=str, default=None,
                       help='Comma-separated list of language codes to keep (e.g., "eng,por,spa"). '
                            'Also keeps unknown/undefined. Default: eng,en,por,pt,english,portuguese')
    
    args = parser.parse_args()
    
    if not args.directory:
        parser.error('directory is required (either as argument or CONVERT_DIRECTORY in .env)')
    
    # Parse languages from command line or environment
    languages = None
    if args.languages:
        languages = [lang.strip() for lang in args.languages.split(',')]
    elif env_languages:
        languages = env_languages
    
    process_directory(args.directory, args.max_parallel, args.temp_directory,
                     args.use_hw_accel, args.hw_accel_type, languages)


if __name__ == '__main__':
    main()
