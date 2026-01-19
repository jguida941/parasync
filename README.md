# ParaSync

Dead simple file sync between Windows and macOS over SSH. Built for Parallels.

![ParaSync Main Interface](imgs/app-screenshot.png)

## Why?

When you're developing in a Windows VM on a Mac (via Parallels), files end up scattered:

- **Build outputs** live on Windows
- **Test scripts** might be on Mac
- **Config files** get edited on both sides
- **Nothing stays in sync** - you forget which version is latest

ParaSync solves this with one-click folder syncing. No shared folders, no cloud services, no confusion about which file is current. Just pick a folder on each side and keep them synced.

## Quick Install (Windows)

Already have Python 3.10+ and Git? One command does everything:

```powershell
irm https://raw.githubusercontent.com/jguida941/parasync/main/install-windows.ps1 | iex
```

This installs, updates, launches the app, and creates a **desktop shortcut**. Run it anytime to update.

---

## The Experience

1. **Double-click ParaSync** on your desktop
2. **App auto-finds your Mac** (scans the Parallels network)
3. **Click "Setup Passwordless"** (one-time, enter Mac password once)
4. **Click Browse** to select a folder
5. **Choose your sync mode:**
   - **SYNC BOTH** - Merge folders (recommended, no deletes)
   - **PUSH** - Mirror Windows → Mac
   - **PULL** - Mirror Mac → Windows

That's it. Folders stay in sync.

---

## Setup Instructions

### MAC SIDE (do first)

#### Step 1: Enable Remote Login (SSH)

1. Open **System Settings**
2. Go to **General** → **Sharing**
3. Turn ON **Remote Login**
4. Make sure your user is allowed (should be by default)

#### Step 2: Create the exchange folder

Open Terminal and run:
```bash
mkdir -p ~/Parallels_EXCHANGE
```

#### Step 3: Verify your Mac's IP (optional)

```bash
ipconfig getifaddr en0
```

Should show something like `10.211.55.2` (the app finds this automatically)

**Mac side is done.**

---

### WINDOWS SIDE (in Parallels)

#### Step 1: Open PowerShell

Press `Win + X` → **Windows PowerShell** (or Terminal)

#### Step 2: Install Python and Git (if not installed)

```powershell
winget install Python.Python.3.12
winget install Git.Git
```

**Close and reopen PowerShell** after installing.

#### Step 3: Run the install script

```powershell
irm https://raw.githubusercontent.com/jguida941/parasync/main/install-windows.ps1 | iex
```

This clones, installs, and launches the app. Run it anytime to update.

**Windows side is done.**

---

## Using the App

### First Time Setup

1. **App opens** → Automatically scans and finds your Mac
2. **Click "Setup Passwordless"** → Enter your Mac password once when prompted
3. **Click Browse** to select your local folder (e.g., your Visual Studio Release folder)
4. **Click "PUSH TO MAC"**

### Every Time After

1. Double-click the **ParaSync** shortcut on your desktop
2. Choose your sync mode:
   - **SYNC BOTH** (recommended) - merges folders, no deletes
   - **PUSH** - mirrors Windows to Mac
   - **PULL** - mirrors Mac to Windows

Push/Pull shows a **diff preview** first so you see exactly what will change. Deleted files go to trash, not permanent delete.

---

## What the App Does Automatically

| Task | How It's Automated |
|------|-------------------|
| Find Mac IP | Scans 10.211.55.x for SSH (port 22) |
| Create SSH key | Generates ed25519 key with no passphrase |
| Install key on Mac | Appends to ~/.ssh/authorized_keys |
| Mirror sync | Cleans destination, then copies all files |

---

## Sync Modes

| Mode | What it does | Deletes files? |
|------|--------------|----------------|
| **SYNC BOTH** | Copies missing files to both sides | No |
| **PUSH** | Makes Mac match Windows exactly | Yes (to trash) |
| **PULL** | Makes Windows match Mac exactly | Yes (to trash) |

**SYNC BOTH** is the safest - it merges both folders without deleting anything.

### SYNC BOTH Example

Before sync - files exist on only one side:

![Before Sync](imgs/pre_sync.png)

After sync - both sides have all files:

![After Sync](imgs/post_sync.png)

### PUSH Example

Push copies Windows → Mac, removing Mac-only files:

![Push Dialog](imgs/windows_to_mac_push.png)

After push - Mac matches Windows:

![After Push](imgs/post_windows_to_mac_push.png)

### PULL Example

Pull copies Mac → Windows, removing Windows-only files:

![Pull Dialog](imgs/pull_from_mac.png)

After pull - Windows matches Mac:

![After Pull](imgs/post_pull_from_mac.png)

---

## GUI Features

- **Three sync modes** - SYNC BOTH (merge), PUSH (mirror to Mac), PULL (mirror to Windows)
- **Auto-detect Mac** - No typing IP addresses
- **File browser panels** - See contents of both local and remote folders
- **Diff preview** - See exactly what will be added/deleted/updated before syncing
- **Safe sync** - Deleted files go to trash (~/.Trash on Mac, ~/.parasync_trash on Windows)
- **One-click passwordless setup** - Never type password again
- **Auto mode** - Automatically copies new Windows files to Mac (one-way, no deletes)
- **Desktop shortcut** - Created automatically by installer
- **Remembers settings** - Saved to ~/.parasync/config.json

---

## Visual Studio Post-Build (Optional)

Auto-push after every build. Add to **Project Properties → Build Events → Post-Build Event**:

```
"C:\Users\YourUsername\repos\parasync\.venv\Scripts\parasync.exe" push --name default
```

---

## CLI Commands (Optional)

The GUI handles everything, but CLI is available:

```powershell
# Test connection
.\.venv\Scripts\parasync test --name default

# Push files
.\.venv\Scripts\parasync push --name default

# Pull files
.\.venv\Scripts\parasync pull --name default
```

---

## Troubleshooting

### "No Mac found on network"
- Enable Remote Login on Mac (System Settings → General → Sharing)
- Make sure you're on the Parallels shared network

### "Permission denied"
- Click "Setup Passwordless" button
- Enter your Mac password when prompted

### SSH key not working
Delete old keys and try again:
```powershell
del $HOME\.ssh\id_ed25519_parasync*
```
Then click "Setup Passwordless" in the app.

### Check if files arrived on Mac
```bash
ls ~/Parallels_EXCHANGE
```

---

## How It Works

```
Windows (Parallels VM)              Mac (Host)
        │                              │
        │  1. Scan 10.211.55.x:22     │
        │ ─────────────────────────▶  │  (finds Mac)
        │                              │
        │  2. ssh-keygen (local)      │
        │                              │
        │  3. ssh: install key        │
        │ ─────────────────────────▶  │  (one-time setup)
        │                              │
        │  PUSH: Clean + Copy         │
        │ ─────────────────────────▶  │  (mirror to Mac)
        │                              │
        │  PULL: Clean + Copy         │
        │ ◀─────────────────────────  │  (mirror to Windows)
        │                              │
```

---

## Files Created

| Location | File | Purpose |
|----------|------|---------|
| Windows | `~/.parasync/config.json` | Saved settings |
| Windows | `~/.parasync_trash/` | Trash for deleted files (from pull) |
| Windows | `~/.ssh/id_ed25519_parasync` | SSH private key |
| Windows | `~/.ssh/id_ed25519_parasync.pub` | SSH public key |
| Mac | `~/.ssh/authorized_keys` | Contains your public key |
| Mac | `~/.Trash/` | Trash for deleted files (from push) |
| Mac | `~/Parallels_EXCHANGE/` | Where files are pushed |

---

## Requirements

- **Mac**: macOS with Remote Login enabled
- **Windows**: Python 3.10+, Git
- **Network**: Parallels shared networking (default)

---

## License

MIT
