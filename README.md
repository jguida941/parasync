# ParaSync

Dead simple file sync between Windows and macOS over SSH. Built for Parallels.

![ParaSync App](imgs/app-screenshot.png)

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
5. **Click PUSH** or **PULL**

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
2. Click **PUSH TO MAC** or **PULL FROM MAC**

Push/Pull does a **true mirror sync** - destination matches source exactly.

---

## What the App Does Automatically

| Task | How It's Automated |
|------|-------------------|
| Find Mac IP | Scans 10.211.55.x for SSH (port 22) |
| Create SSH key | Generates ed25519 key with no passphrase |
| Install key on Mac | Appends to ~/.ssh/authorized_keys |
| Mirror sync | Cleans destination, then copies all files |

---

## GUI Features

- **Auto-detect Mac** - No typing IP addresses
- **File browser panels** - See contents of both local and remote folders
- **True mirror sync** - Push/Pull makes destination match source exactly
- **One-click passwordless setup** - Never type password again
- **Watch mode** - Auto-push when local folder changes (checkbox)
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
| Windows | `~/.ssh/id_ed25519_parasync` | SSH private key |
| Windows | `~/.ssh/id_ed25519_parasync.pub` | SSH public key |
| Mac | `~/.ssh/authorized_keys` | Contains your public key |
| Mac | `~/Parallels_EXCHANGE/` | Where files are pushed |

---

## Requirements

- **Mac**: macOS with Remote Login enabled
- **Windows**: Python 3.10+, Git
- **Network**: Parallels shared networking (default)

---

## License

MIT
