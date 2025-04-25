# Define the directory to search for MP4 and MKV files
param(
    [string]$directory = "S:\Recent\AAC",
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
    # Use the input file from the parallel block
    $file = $_

    # Extract filename without extension
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($file.FullName)
    $dirName = $file.DirectoryName

    # Define the output file name for the converted file
    $tempOutputFile = "$dirName\$baseName`_ac3$($file.Extension)"
    $originalFileRenamed = "$dirName\$baseName`_old$($file.Extension)"

    Write-Host "Processing: $file"

    # Run ffmpeg to convert the audio to AC3, keeping other streams intact
    $ffmpegCmd = "ffmpeg -i `"$($file.FullName)`" -map 0:v -map 0:a -map 0:s? -c:v copy -c:a ac3 -b:a 640k -c:s copy  `"$tempOutputFile`""
	
    Invoke-Expression $ffmpegCmd

    # Check if conversion was successful
    if (Test-Path -Path $tempOutputFile) {
        # Rename original file to append '_old'
        Rename-Item -Path $file.FullName -NewName $originalFileRenamed

        # Rename the converted file to the original file name
        Rename-Item -Path $tempOutputFile -NewName $file.FullName

        Write-Host "Successfully converted and renamed: $file"
    } else {
        Write-Host "Failed to convert: $file"
    }
} -ThrottleLimit $maxParallel
