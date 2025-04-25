# Define your TMDb API key and the directory containing movie files
$ApiKey = "KEY" # Replace with your TMDb API key
$DirectoryPath = "S:\Movies\" # Replace with your directory path
$TrailerDirectory = "S:\Trailers"


if (-not (Test-Path -Path $TrailerDirectory)) {
    New-Item -ItemType Directory -Path $TrailerDirectory | Out-Null
}

# Enumerate movie files
$MovieFiles = Get-ChildItem -Path $DirectoryPath -Recurse -Include *.mp4, *.mkv, *.avi

function Get-MovieTrailerUrl {
    param (
        [string]$MovieName
    )

    $SearchUrl = "https://api.themoviedb.org/3/search/movie?api_key=$ApiKey&query=$( [uri]::EscapeDataString($MovieName) )"
    $SearchResult = Invoke-RestMethod -Uri $SearchUrl -Method Get

    if ($SearchResult.results.Count -gt 0) {
        $MovieId = $SearchResult.results[0].id
        $VideosUrl = "https://api.themoviedb.org/3/movie/$MovieId/videos?api_key=$ApiKey"
        $VideoResult = Invoke-RestMethod -Uri $VideosUrl -Method Get

        $Trailer = $VideoResult.results | Where-Object { $_.type -eq "Trailer" -and $_.site -eq "YouTube" } | Select-Object -First 1

        if ($Trailer) {
            return "https://www.youtube.com/watch?v=$($Trailer.key)"
        }
    }
    return $null
}

# Function to parse the original title from NFO file
function Get-MovieNameFromNFO {
    param (
        [string]$NFOFilePath
    )

    if (Test-Path -LiteralPath $NFOFilePath) {
        try {
            Write-Host "Processing file: $NFOFilePath"
            $NFOContent = [xml](Get-Content -LiteralPath $NFOFilePath -ErrorAction Stop)
            if ($NFOContent.movie.originaltitle) {
                return $NFOContent.movie.originaltitle
            }
        } catch {
            Write-Warning "Failed to parse NFO file: $NFOFilePath"
        }
    }
    return $null
}

# Function to download YouTube video as MP4
function Download-YouTubeVideo {
    param (
        [string]$YouTubeUrl,
        [string]$OutputPath
    )

    # Requires yt-dlp installed and available in PATH
    yt-dlp --cookies-from-browser firefox -f mp4 --cookies cookies.txt -o $OutputPath $YouTubeUrl --sub-langs pt.* 
}

function Sanitize-FileName {
    param (
        [string]$FileName,
        [string]$ReplacementChar = ""
    )

    # Define a regex pattern for invalid characters
    $InvalidChars = '[<>:"/\\\\|?*]'
    
    # Replace invalid characters with the specified replacement character
    return $FileName -replace $InvalidChars, $ReplacementChar
}


foreach ($MovieFile in $MovieFiles) {
    # Extract the NFO file path
    $NFOFilePath = [System.IO.Path]::ChangeExtension($MovieFile.FullName, ".nfo")

    # Get the movie name from the NFO file, fallback to file name if necessary
    $MovieName = Get-MovieNameFromNFO -NFOFilePath $NFOFilePath
    if (-not $MovieName) {
        $MovieName = [System.IO.Path]::GetFileNameWithoutExtension($MovieFile.Name)
    }

    # Get the trailer URL
    $TrailerUrl = Get-MovieTrailerUrl -MovieName $MovieName

    if ($TrailerUrl) {
        Write-Host "Found trailer for '$MovieName': $TrailerUrl"

        # Set output file path for the trailer
        $OutputPath = Join-Path -Path $TrailerDirectory -ChildPath "$(Sanitize-FileName $MovieName).mp4"

        # Download the trailer as MP4 using yt-dlp
        Download-YouTubeVideo -YouTubeUrl $TrailerUrl -OutputPath $OutputPath
        Write-Host "Trailer downloaded to: $OutputPath"
    } else {
        Write-Warning "No trailer found for '$MovieName'."
    }
}
