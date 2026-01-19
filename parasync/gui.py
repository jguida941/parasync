"""
ParaSync GUI - Dead simple file sync between Windows and macOS.

Features:
- Shows both local and remote folder contents
- No terminal commands needed
- Auto-detects Mac on Parallels network
- One-click push/pull
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import threading
import os
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, Profile, get_profile, load_config, save_config, upsert_profile
from .util import default_config_path, is_windows


def scan_for_ssh_host(subnet: str = "10.211.55", timeout: float = 0.5) -> Optional[str]:
    """Scan Parallels subnet for SSH host."""
    candidates = [f"{subnet}.2", f"{subnet}.1", f"{subnet}.3"]
    for i in range(4, 20):
        candidates.append(f"{subnet}.{i}")

    for ip in candidates:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, 22))
            sock.close()
            if result == 0:
                return ip
        except:
            pass
    return None


def get_current_username() -> str:
    return os.environ.get("USER") or os.environ.get("USERNAME") or "user"


class WorkerSignals(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(str)
    file_list = pyqtSignal(list)  # For returning file listings


class SyncWorker(threading.Thread):
    """Background worker for all operations."""

    def __init__(self, signals: WorkerSignals, operation: str,
                 host: str = "", user: str = "", local_path: str = "",
                 remote_path: str = "", identity_file: str = ""):
        super().__init__(daemon=True)
        self.signals = signals
        self.operation = operation
        self.host = host
        self.user = user
        self.local_path = local_path
        self.remote_path = remote_path
        self.identity_file = identity_file

    def _run_cmd(self, cmd: list[str], timeout: int = 300) -> tuple[bool, str, str]:
        self.signals.log.emit(f"$ {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    def _ssh_args(self, batch_mode: bool = True) -> list[str]:
        args = ["ssh"]
        if batch_mode:
            args += ["-o", "BatchMode=yes"]
        args += ["-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
        if self.identity_file:
            args += ["-i", self.identity_file]
        return args

    def _scp_args(self) -> list[str]:
        args = ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-o", "StrictHostKeyChecking=accept-new", "-r"]
        if self.identity_file:
            args += ["-i", self.identity_file]
        return args

    def _remote(self) -> str:
        return f"{self.user}@{self.host}"

    def run(self):
        ops = {
            "scan": self._do_scan,
            "test": self._do_test,
            "setup": self._do_full_setup,
            "push": self._do_push,
            "pull": self._do_pull,
            "list_remote": self._do_list_remote,
        }
        if self.operation in ops:
            ops[self.operation]()

    def _do_scan(self):
        self.signals.progress.emit("Scanning for Mac...")
        ip = scan_for_ssh_host()
        if ip:
            self.signals.finished.emit(True, ip)
        else:
            self.signals.finished.emit(False, "No Mac found. Is Remote Login enabled?")

    def _do_test(self):
        self.signals.progress.emit("Testing SSH...")
        cmd = self._ssh_args() + [self._remote(), "echo", "SSH_OK"]
        ok, out, err = self._run_cmd(cmd, timeout=15)
        if ok and "SSH_OK" in out:
            self.signals.finished.emit(True, "Connected!")
        else:
            if "Permission denied" in err:
                self.signals.finished.emit(False, "Need to setup passwordless SSH first.")
            else:
                self.signals.finished.emit(False, f"Connection failed: {err or out}")

    def _do_full_setup(self):
        key_path = Path.home() / ".ssh" / "id_ed25519_parasync"
        pub_path = key_path.with_suffix(".pub")

        if not key_path.exists():
            self.signals.progress.emit("Generating SSH key...")
            key_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["ssh-keygen", "-t", "ed25519", "-C", "parasync", "-f", str(key_path), "-N", ""]
            ok, out, err = self._run_cmd(cmd, timeout=30)
            if not ok:
                self.signals.finished.emit(False, f"Failed to generate key: {err}")
                return

        self.signals.progress.emit("Installing key on Mac (enter password if prompted)...")
        pubkey = pub_path.read_text().strip()
        ssh_args = ["ssh", "-o", "ConnectTimeout=30", "-o", "StrictHostKeyChecking=accept-new"]
        remote_cmd = (
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            f"grep -qxF '{pubkey}' ~/.ssh/authorized_keys 2>/dev/null || "
            f"echo '{pubkey}' >> ~/.ssh/authorized_keys && "
            "chmod 600 ~/.ssh/authorized_keys && echo SETUP_OK"
        )
        cmd = ssh_args + [self._remote(), remote_cmd]
        ok, out, err = self._run_cmd(cmd, timeout=60)

        if ok and "SETUP_OK" in out:
            self.signals.progress.emit("Verifying...")
            self.identity_file = str(key_path)
            test_cmd = self._ssh_args(batch_mode=True) + [self._remote(), "echo", "KEY_OK"]
            ok2, out2, err2 = self._run_cmd(test_cmd, timeout=15)
            if ok2 and "KEY_OK" in out2:
                self.signals.finished.emit(True, "Setup complete!")
            else:
                self.signals.finished.emit(False, f"Key installed but verification failed: {err2}")
        else:
            self.signals.finished.emit(False, f"Failed to install key: {err or out}")

    def _do_push(self):
        local = Path(self.local_path)
        if not local.exists():
            self.signals.finished.emit(False, f"Local path not found: {local}")
            return

        # Clean and recreate remote folder for true mirror
        self.signals.progress.emit("Cleaning remote folder...")
        clean_cmd = self._ssh_args() + [self._remote(),
            f"rm -rf '{self.remote_path}' && mkdir -p '{self.remote_path}'"]
        ok, out, err = self._run_cmd(clean_cmd, timeout=30)
        if not ok:
            self.signals.finished.emit(False, f"Failed to prepare remote folder: {err}")
            return

        # Copy all contents
        self.signals.progress.emit("Syncing files to Mac...")
        files = list(local.iterdir())
        if not files:
            self.signals.finished.emit(True, "Pushed: (empty folder)")
            return

        # Copy each item in the folder
        for item in files:
            scp_cmd = self._scp_args() + [str(item), f"{self._remote()}:{self.remote_path}/"]
            ok, out, err = self._run_cmd(scp_cmd, timeout=600)
            if not ok:
                self.signals.finished.emit(False, f"Push failed on {item.name}: {err}")
                return

        self.signals.finished.emit(True, f"Synced: {len(files)} items → Mac")

    def _do_pull(self):
        local = Path(self.local_path)

        # Clean local folder for true mirror
        self.signals.progress.emit("Cleaning local folder...")
        if local.exists():
            for item in local.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        local.mkdir(parents=True, exist_ok=True)

        # Get list of remote files
        self.signals.progress.emit("Syncing files from Mac...")
        scp_cmd = self._scp_args() + [f"{self._remote()}:{self.remote_path}/*", str(local)]
        ok, out, err = self._run_cmd(scp_cmd, timeout=600)

        if ok:
            self.signals.finished.emit(True, f"Synced from Mac → {local.name}")
        elif "No such file" in err or not err.strip():
            self.signals.finished.emit(True, "Pulled: (remote folder empty)")
        else:
            self.signals.finished.emit(False, f"Pull failed: {err}")

    def _do_list_remote(self):
        """List files in remote directory."""
        self.signals.progress.emit("Reading Mac folder...")
        cmd = self._ssh_args() + [self._remote(), f"ls -1 '{self.remote_path}' 2>/dev/null || echo ''"]
        ok, out, err = self._run_cmd(cmd, timeout=15)
        if ok:
            files = [f for f in out.strip().split('\n') if f]
            self.signals.file_list.emit(files)
            self.signals.finished.emit(True, "")
        else:
            self.signals.file_list.emit([])
            self.signals.finished.emit(False, err)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ParaSync")

        # State
        self.mac_ip: str = ""
        self.mac_user: str = get_current_username()
        self.ssh_ok: bool = False
        self.key_ok: bool = False
        self.local_path: str = ""
        self.remote_path: str = f"/Users/{self.mac_user}/Parallels_EXCHANGE"

        # Config
        self.cfg_path = Path(default_config_path())
        self.cfg = load_config(self.cfg_path)

        prof = get_profile(self.cfg, "default")
        if prof:
            self.mac_ip = prof.host
            self.mac_user = prof.user
            self.local_path = prof.local_path or ""
            self.remote_path = prof.remote_path or self.remote_path

        # Worker signals
        self.signals = WorkerSignals()
        self.signals.log.connect(self._log)
        self.signals.finished.connect(self._on_worker_finished)
        self.signals.progress.connect(self._on_progress)
        self.signals.file_list.connect(self._on_remote_file_list)

        self.current_worker: Optional[SyncWorker] = None
        self.pending_operation: str = ""

        # File watcher
        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self._on_watch_triggered)
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._do_auto_push)
        self.watching = False

        self._build_ui()

        if not self.mac_ip:
            QTimer.singleShot(500, self._do_scan)
        else:
            self._update_status()
            QTimer.singleShot(500, self._refresh_both)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)

        # === STATUS BAR ===
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(status_frame)

        status_layout.addWidget(QLabel("Mac:"))
        self.lbl_mac = QLabel("Scanning...")
        self.lbl_mac.setFont(QFont("", -1, QFont.Weight.Bold))
        status_layout.addWidget(self.lbl_mac)

        status_layout.addWidget(QLabel("SSH:"))
        self.lbl_ssh = QLabel("-")
        status_layout.addWidget(self.lbl_ssh)

        status_layout.addStretch()

        self.btn_setup = QPushButton("Setup Passwordless")
        self.btn_setup.clicked.connect(self._do_setup)
        status_layout.addWidget(self.btn_setup)

        self.btn_rescan = QPushButton("Rescan")
        self.btn_rescan.clicked.connect(self._do_scan)
        status_layout.addWidget(self.btn_rescan)

        layout.addWidget(status_frame)

        # === FILE BROWSERS ===
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Local (Windows)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("LOCAL (Windows):"))
        self.lbl_local_path = QLabel("Not set")
        self.lbl_local_path.setStyleSheet("color: gray;")
        left_header.addWidget(self.lbl_local_path, 1)
        self.btn_browse_local = QPushButton("Browse...")
        self.btn_browse_local.clicked.connect(self._browse_local)
        left_header.addWidget(self.btn_browse_local)
        self.btn_refresh_local = QPushButton("↻")
        self.btn_refresh_local.setFixedWidth(30)
        self.btn_refresh_local.clicked.connect(self._refresh_local)
        left_header.addWidget(self.btn_refresh_local)
        left_layout.addLayout(left_header)

        self.list_local = QListWidget()
        self.list_local.setMinimumHeight(150)
        left_layout.addWidget(self.list_local)

        splitter.addWidget(left_widget)

        # Right: Remote (Mac)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_header = QHBoxLayout()
        right_header.addWidget(QLabel("REMOTE (Mac):"))
        self.lbl_remote_path = QLabel(self.remote_path)
        self.lbl_remote_path.setStyleSheet("color: gray;")
        right_header.addWidget(self.lbl_remote_path, 1)
        self.btn_edit_remote = QPushButton("Edit...")
        self.btn_edit_remote.clicked.connect(self._edit_remote_path)
        right_header.addWidget(self.btn_edit_remote)
        self.btn_refresh_remote = QPushButton("↻")
        self.btn_refresh_remote.setFixedWidth(30)
        self.btn_refresh_remote.clicked.connect(self._refresh_remote)
        right_header.addWidget(self.btn_refresh_remote)
        right_layout.addLayout(right_header)

        self.list_remote = QListWidget()
        self.list_remote.setMinimumHeight(150)
        right_layout.addWidget(self.list_remote)

        splitter.addWidget(right_widget)
        layout.addWidget(splitter)

        # === ACTION BUTTONS ===
        btn_layout = QHBoxLayout()

        self.btn_push = QPushButton("PUSH TO MAC →")
        self.btn_push.setMinimumHeight(50)
        self.btn_push.setFont(QFont("", 14, QFont.Weight.Bold))
        self.btn_push.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.btn_push.clicked.connect(self._do_push)
        btn_layout.addWidget(self.btn_push)

        self.btn_pull = QPushButton("← PULL FROM MAC")
        self.btn_pull.setMinimumHeight(50)
        self.btn_pull.setFont(QFont("", 14, QFont.Weight.Bold))
        self.btn_pull.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        self.btn_pull.clicked.connect(self._do_pull)
        btn_layout.addWidget(self.btn_pull)

        layout.addLayout(btn_layout)

        # === WATCH MODE ===
        watch_layout = QHBoxLayout()
        self.chk_watch = QCheckBox("Auto-push when local folder changes")
        self.chk_watch.stateChanged.connect(self._toggle_watch)
        watch_layout.addWidget(self.chk_watch)
        self.lbl_watch = QLabel("")
        watch_layout.addWidget(self.lbl_watch, 1)
        layout.addLayout(watch_layout)

        # === PROGRESS ===
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        # === LOG ===
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(80)
        self.log_box.setPlaceholderText("Activity log...")
        layout.addWidget(self.log_box)

        # Update display
        if self.local_path:
            self.lbl_local_path.setText(self.local_path)
            self._refresh_local()

    def _log(self, msg: str):
        self.log_box.appendPlainText(msg)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_status(self):
        if self.mac_ip:
            self.lbl_mac.setText(f"{self.mac_user}@{self.mac_ip}")
            self.lbl_mac.setStyleSheet("color: green;")
        else:
            self.lbl_mac.setText("Not found")
            self.lbl_mac.setStyleSheet("color: red;")

        if self.key_ok:
            self.lbl_ssh.setText("Passwordless OK")
            self.lbl_ssh.setStyleSheet("color: green;")
            self.btn_setup.setEnabled(False)
            self.btn_setup.setText("Ready")
        elif self.ssh_ok:
            self.lbl_ssh.setText("Connected")
            self.lbl_ssh.setStyleSheet("color: orange;")
            self.btn_setup.setEnabled(True)
        else:
            self.lbl_ssh.setText("Not connected")
            self.lbl_ssh.setStyleSheet("color: gray;")
            self.btn_setup.setEnabled(bool(self.mac_ip))

    def _set_busy(self, busy: bool, message: str = ""):
        self.btn_push.setEnabled(not busy)
        self.btn_pull.setEnabled(not busy)
        self.btn_setup.setEnabled(not busy and not self.key_ok)
        self.btn_rescan.setEnabled(not busy)
        self.btn_refresh_local.setEnabled(not busy)
        self.btn_refresh_remote.setEnabled(not busy)

        if busy:
            self.progress.show()
            self.progress.setFormat(message)
        else:
            self.progress.hide()

    def _on_progress(self, message: str):
        self.progress.setFormat(message)

    def _on_worker_finished(self, success: bool, message: str):
        self._set_busy(False)
        op = self.pending_operation
        self.current_worker = None
        self.pending_operation = ""

        if op == "scan":
            if success:
                self.mac_ip = message
                self._log(f"Found Mac at {message}")
                self._save_profile()
                self._update_status()
                self._do_test()
            else:
                self._log(message)
                self._update_status()

        elif op == "test":
            if success:
                self.ssh_ok = True
                key_path = Path.home() / ".ssh" / "id_ed25519_parasync"
                if key_path.exists():
                    self.key_ok = True
                self._update_status()
                self._refresh_remote()
            else:
                self.ssh_ok = False
                self.key_ok = False
                self._log(message)
                self._update_status()

        elif op == "setup":
            if success:
                self.key_ok = True
                self._log(message)
                self._update_status()
                self._save_profile()
                self._refresh_remote()
            else:
                self._log(f"Setup failed: {message}")
                QMessageBox.warning(self, "Setup Failed", message)

        elif op == "push":
            if success:
                self._log(message)
                self._refresh_remote()
            else:
                self._log(f"Failed: {message}")
                QMessageBox.warning(self, "Push Failed", message)

        elif op == "pull":
            if success:
                self._log(message)
                self._refresh_local()
            else:
                self._log(f"Failed: {message}")
                QMessageBox.warning(self, "Pull Failed", message)

        elif op == "list_remote":
            if not success and message:
                self._log(f"Failed to list remote: {message}")

    def _on_remote_file_list(self, files: list):
        self.list_remote.clear()
        if not files:
            item = QListWidgetItem("(empty)")
            item.setForeground(Qt.GlobalColor.gray)
            self.list_remote.addItem(item)
        else:
            for f in files:
                self.list_remote.addItem(f)

    def _run_worker(self, operation: str, **kwargs):
        if self.current_worker and self.current_worker.is_alive():
            return

        self.pending_operation = operation
        key_path = Path.home() / ".ssh" / "id_ed25519_parasync"
        identity = str(key_path) if key_path.exists() else ""

        self._set_busy(True, f"{operation.replace('_', ' ').title()}...")
        self.current_worker = SyncWorker(
            self.signals, operation,
            host=kwargs.get("host", self.mac_ip),
            user=kwargs.get("user", self.mac_user),
            local_path=kwargs.get("local_path", self.local_path),
            remote_path=kwargs.get("remote_path", self.remote_path),
            identity_file=kwargs.get("identity_file", identity),
        )
        self.current_worker.start()

    def _do_scan(self):
        self._run_worker("scan")

    def _do_test(self):
        if self.mac_ip:
            self._run_worker("test")

    def _do_setup(self):
        if not self.mac_ip:
            QMessageBox.warning(self, "No Mac", "Scan for Mac first.")
            return
        reply = QMessageBox.question(
            self, "Setup Passwordless SSH",
            f"This will setup passwordless SSH to {self.mac_user}@{self.mac_ip}.\n\n"
            "You'll enter your Mac password once.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_worker("setup")

    def _do_push(self):
        if not self.mac_ip:
            QMessageBox.warning(self, "No Mac", "Scan for Mac first.")
            return
        if not self.local_path:
            QMessageBox.warning(self, "No Local Path", "Select a local folder first (click Browse).")
            return
        if not self.key_ok and not self.ssh_ok:
            QMessageBox.warning(self, "Not Connected", "Setup SSH connection first.")
            return
        reply = QMessageBox.warning(
            self, "Confirm Push",
            f"This will DELETE everything in:\n{self.remote_path}\n\n"
            f"And replace it with contents of:\n{self.local_path}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_worker("push")

    def _do_pull(self):
        if not self.mac_ip:
            QMessageBox.warning(self, "No Mac", "Scan for Mac first.")
            return
        if not self.local_path:
            QMessageBox.warning(self, "No Local Path", "Select a local destination folder first (click Browse).")
            return
        if not self.key_ok and not self.ssh_ok:
            QMessageBox.warning(self, "Not Connected", "Setup SSH connection first.")
            return
        reply = QMessageBox.warning(
            self, "Confirm Pull",
            f"This will DELETE everything in:\n{self.local_path}\n\n"
            f"And replace it with contents of:\n{self.remote_path}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_worker("pull")

    def _browse_local(self):
        path = QFileDialog.getExistingDirectory(self, "Select Local Folder", str(Path.home()))
        if path:
            self.local_path = path
            self.lbl_local_path.setText(path)
            self._save_profile()
            self._refresh_local()

    def _edit_remote_path(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Remote Path")
        layout = QFormLayout(dialog)

        path_edit = QLineEdit(self.remote_path)
        layout.addRow("Remote Path:", path_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.remote_path = path_edit.text().strip()
            self.lbl_remote_path.setText(self.remote_path)
            self._save_profile()
            self._refresh_remote()

    def _refresh_local(self):
        self.list_local.clear()
        if not self.local_path:
            item = QListWidgetItem("(no folder selected)")
            item.setForeground(Qt.GlobalColor.gray)
            self.list_local.addItem(item)
            return

        local = Path(self.local_path)
        if not local.exists():
            item = QListWidgetItem("(folder not found)")
            item.setForeground(Qt.GlobalColor.red)
            self.list_local.addItem(item)
            return

        files = list(local.iterdir())
        if not files:
            item = QListWidgetItem("(empty)")
            item.setForeground(Qt.GlobalColor.gray)
            self.list_local.addItem(item)
        else:
            for f in sorted(files, key=lambda x: x.name.lower()):
                name = f.name + ("/" if f.is_dir() else "")
                self.list_local.addItem(name)

    def _refresh_remote(self):
        if self.mac_ip and (self.ssh_ok or self.key_ok):
            self._run_worker("list_remote")
        else:
            self.list_remote.clear()
            item = QListWidgetItem("(not connected)")
            item.setForeground(Qt.GlobalColor.gray)
            self.list_remote.addItem(item)

    def _refresh_both(self):
        self._refresh_local()
        self._refresh_remote()

    def _save_profile(self):
        prof = Profile(
            name="default",
            host=self.mac_ip,
            user=self.mac_user,
            port=22,
            local_path=self.local_path,
            remote_path=self.remote_path,
            identity_file=str(Path.home() / ".ssh" / "id_ed25519_parasync"),
            ensure_remote_dir=True,
        )
        upsert_profile(self.cfg, prof)
        save_config(self.cfg, self.cfg_path)

    def _toggle_watch(self, state: int):
        if state == Qt.CheckState.Checked.value:
            self._start_watch()
        else:
            self._stop_watch()

    def _start_watch(self):
        if not self.local_path:
            QMessageBox.warning(self, "No Folder", "Select a local folder first.")
            self.chk_watch.setChecked(False)
            return
        if self.file_watcher.addPath(self.local_path):
            self.watching = True
            self.lbl_watch.setText("Watching...")
            self._log(f"Watching: {self.local_path}")
        else:
            self.chk_watch.setChecked(False)

    def _stop_watch(self):
        for p in self.file_watcher.directories():
            self.file_watcher.removePath(p)
        self.watching = False
        self.lbl_watch.setText("")

    def _on_watch_triggered(self, path: str):
        if self.watching:
            self._log(f"Change detected: {path}")
            self.debounce_timer.start(2000)

    def _do_auto_push(self):
        if self.watching and not self.current_worker:
            self._log("Auto-pushing...")
            self._do_push()

    def closeEvent(self, event):
        self._stop_watch()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ParaSync")
    w = MainWindow()
    w.resize(700, 550)
    w.show()
    return app.exec()
