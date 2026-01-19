$RepoDir = "$HOME\repos\parasync"

# Clone or pull
if (Test-Path $RepoDir) {
    Set-Location $RepoDir
    git pull
} else {
    New-Item -ItemType Directory -Path "$HOME\repos" -Force | Out-Null
    git clone https://github.com/jguida941/parasync.git $RepoDir
    Set-Location $RepoDir
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Always reinstall (catches updates)
.\.venv\Scripts\pip install -e . --quiet

# Create desktop shortcut
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$Desktop\ParaSync.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$RepoDir\.venv\Scripts\parasync-gui.exe"
$Shortcut.WorkingDirectory = $RepoDir
$Shortcut.Save()

# Launch the app
.\.venv\Scripts\parasync-gui
