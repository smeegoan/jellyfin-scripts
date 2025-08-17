# Jellyfin Scripts

A collection of PowerShell scripts designed to enhance and automate tasks for your Jellyfin media server.

## Scripts

### ConvertToAC3.ps1

This script converts audio tracks of media files to the AC3 format, ensuring better compatibility across various playback devices.

### DownloadTrailers.ps1

Automatically downloads movie trailers for your media library, enriching the viewing experience within Jellyfin.

## Prerequisites

- Windows operating system with PowerShell installed.
- FFmpeg must be installed and accessible via the system's PATH.

## Usage

1. **Clone the repository**:

   ```bash
   git clone https://github.com/smeegoan/jellyfin-scripts.git
   ```

2. **Navigate to the cloned directory**:

   ```bash
   cd jellyfin-scripts
   ```

3. **Run the desired script using PowerShell**:

   ```powershell
   .\ConvertToAC3.ps1
   ```

   or

   ```powershell
   .\DownloadTrailers.ps1
   ```

Ensure you review and, if necessary, modify the scripts to fit your specific directory structures and requirements.

## License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/smeegoan/jellyfin-scripts/blob/main/LICENSE) file for details.
