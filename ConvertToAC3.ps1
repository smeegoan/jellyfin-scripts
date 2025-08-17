param(
    [string]$directory = "S:\Series\Alien.Earth",
    [int]$maxParallel = 1  # Maximum number of parallel jobs
)

# Check if the directory exists
if (-Not (Test-Path -Path $directory)) {
    Write-Host "The specified directory does not exist."
    exit
}

# Get all MP4 and MKV files in the directory and subdirectories
$videoFiles = Get-ChildItem -Path $directory -Recurse -Include *.mp4, *.mkv

# Process files in parallel
$videoFiles | ForEach-Object -Parallel {
    $file = $_
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.FullName)
    $dirName = $file.DirectoryName

    # Define the output file names
    $tempOutputFile = "$dirName\$baseName`_converted$($file.Extension)"
    $originalFileRenamed = "$dirName\$baseName`_old$($file.Extension)"

    Write-Host "Checking: $($file.Name)"

    # Get information about all audio streams for the file
    # Using an argument array with the call operator (&) is the most robust way to handle file paths with spaces.
    # The output format is set to `default=noprint_wrappers=1:nokey=1`, which provides raw index and codec names.
    $ffprobeArgs = @(
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name",
        "-of", "default=noprint_wrappers=1:nokey=1",
        $file.FullName
    )
    $audioStreamsInfo = & ffprobe @ffprobeArgs 2>&1

    # Check for ffprobe errors. A non-zero exit code means an error occurred.
    if ($LASTEXITCODE -ne 0) {
        Write-Error "FFprobe failed for $($file.Name) with error code $LASTEXITCODE. Output: $($audioStreamsInfo | Out-String)"
        return # Skip to the next file if ffprobe fails
    }

    # Debugging: Print raw ffprobe output to see what is being parsed.
    Write-Host "--- Raw ffprobe Output for $($file.Name) ---"
    Write-Host "$audioStreamsInfo"
    Write-Host "--- End Raw ffprobe Output ---"

    # The `ffprobe` output provides the index and codec on separate lines.
    # We must read the lines in pairs to correctly parse them.
    $lines = $audioStreamsInfo -split "`n" | Where-Object { $_.Trim() -ne "" }
    $audioStreams = @() # Initialize an empty array to hold parsed stream objects

    for ($i = 0; $i -lt $lines.Count; $i += 2) {
        if (($i + 1) -lt $lines.Count) { # Ensure there's a pair of lines (index and codec)
            $index = $lines[$i].Trim()
            $codec = $lines[$i + 1].Trim().ToLower()

            $streamObject = [PSCustomObject]@{
                Index = $index
                Codec = $codec
            }
            Write-Host ("Parsed Stream: Index {0}, Codec {1}" -f $streamObject.Index, $streamObject.Codec) # Debug parsed object
            $audioStreams += $streamObject
        } else {
            Write-Host "Warning: Found an odd number of lines in ffprobe output. Skipping last line: '$($lines[$i])'"
        }
    }
    
    # Determine if any audio stream needs conversion. This check is based on your initial criteria.
    $audioStreamsToConvert = $audioStreams | Where-Object { $_.Codec -notin @("ac3", "eac3") }

    # Build the strings for output outside of the Write-Host call to avoid parsing errors.
    $detectedStreamsString = ($audioStreams | ForEach-Object { "$($_.Codec) (index $($_.Index))" }) -join ', '
    $streamsToConvertString = ($audioStreamsToConvert | ForEach-Object { "$($_.Codec) (index $($_.Index))" }) -join ', '

    Write-Host "Audio streams detected: $detectedStreamsString"
    Write-Host "Audio streams flagged for conversion: $streamsToConvertString"

    Write-Host "Number of streams to convert: $($audioStreamsToConvert.Count)"


    # If there are no audio streams that need conversion, skip the file
    if ($audioStreamsToConvert.Count -eq 0) {
        Write-Host "Skipping: $($file.Name) (all audio streams are already AC3 or E-AC3, or no audio streams found that require conversion)"
        return # Skip to the next file
    }

    Write-Host "Processing: $($file.Name)"
    
    # --- START OF MODIFIED FFmpeg COMMAND CONSTRUCTION ---
    # The most reliable method is to use a global map and then override specific stream codecs.
    $ffmpegArgs = @(
        "-i", $file.FullName,
        "-map", "0:v", # Map all video streams
        "-map", "0:a", # Map all audio streams
        "-map", "0:s?",  # Map all subtitles, if they exist
        "-c:v", "copy", # Copy video streams
        "-c:a", "ac3", "-b:a", "640k", # Convert audio to AC3 with bitrate
        "-c:s", "copy", # Copy subtitle streams
        $tempOutputFile # Add the output file at the end
    )
    # --- END OF MODIFIED FFmpeg COMMAND CONSTRUCTION ---

    Write-Host "Executing command: ffmpeg $($ffmpegArgs -join ' ')"
    $ffmpegResult = & ffmpeg @ffmpegArgs

    # Check ffmpeg's exit code for success
    if ($LASTEXITCODE -ne 0) {
        Write-Error "FFmpeg command failed for $($file.Name) with error code $LASTEXITCODE. Output: $($ffmpegResult | Out-String)"
        # Clean up the partially created temp file
        if (Test-Path -Path $tempOutputFile) {
            Remove-Item -Path $tempOutputFile -Force -ErrorAction SilentlyContinue
        }
        return
    }

    # Check if conversion was successful by verifying the output file exists
    if (Test-Path -Path $tempOutputFile) {
        Rename-Item -Path $file.FullName -NewName $originalFileRenamed -Force
        Rename-Item -Path $tempOutputFile -NewName $file.FullName -Force
        Write-Host "Successfully processed: $($file.Name)"
    } else {
        Write-Host "Failed to convert: $($file.Name) (Output file not found after FFmpeg execution)"
    }
} -ThrottleLimit $maxParallel
