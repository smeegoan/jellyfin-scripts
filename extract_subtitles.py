import os
import subprocess
import sys

def extract_subtitles(input_file, output_dir):
    """
    Extracts all embedded subtitles from a media file using ffmpeg.

    Args:
        input_file (str): Path to the input media file.
        output_dir (str): Directory where the extracted subtitles will be saved.

    Returns:
        None
    """
    try:
        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Run ffmpeg to list subtitle streams
        ffprobe_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "csv=p=0",
            input_file
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, encoding='utf-8', errors='replace', check=True)
        subtitle_text = result.stdout or ''
        subtitle_streams = [line for line in subtitle_text.strip().split('\n') if line]

        if not subtitle_streams or subtitle_streams == ['']:
            print("No subtitles found in the file.")
            return

        # Extract each subtitle stream
        for stream_info in subtitle_streams:
            stream_parts = stream_info.split(",")
            stream_index = stream_parts[0]
            language = stream_parts[1] if len(stream_parts) > 1 else "unknown"
            output_file = os.path.join(output_dir, f"subtitle_{stream_index}_{language}.sup")

            ffmpeg_cmd = [
                "ffmpeg",
                "-i", input_file,
                "-map", f"0:{stream_index}",
                "-c:s", "copy",
                output_file
            ]

            subprocess.run(ffmpeg_cmd, check=True)
            print(f"Extracted subtitle stream {stream_index} ({language}) to {output_file}")

    except subprocess.CalledProcessError as e:
        print(f"Error during processing: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_subtitles.py <input_file> <output_dir>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    extract_subtitles(input_file, output_dir)