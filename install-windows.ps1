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

# Create desktop shortcut (uses pythonw so no console window)
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = "$Desktop\ParaSync.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$RepoDir\.venv\Scripts\pythonw.exe"
$Shortcut.Arguments = "-m parasync.gui"
$Shortcut.WorkingDirectory = $RepoDir
$Shortcut.Save()
Write-Host "Desktop shortcut created!"

# Launch the app (detached from console)
Start-Process "$RepoDir\.venv\Scripts\pythonw.exe" -ArgumentList "-m parasync.gui"
