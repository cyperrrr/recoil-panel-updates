import argparse
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import time


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def is_valid_pe(path: str) -> bool:
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) < 1024:
            return False
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


def wait_for_process_exit(pid: int, timeout: float = 25.0) -> None:
    if not pid or pid <= 0:
        return
    deadline = time.monotonic() + timeout
    if os.name == "nt":
        SYNCHRONIZE = 0x00100000
        WAIT_OBJECT_0 = 0x00000000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return
        try:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if kernel32.WaitForSingleObject(handle, remaining_ms) != WAIT_OBJECT_0:
                time.sleep(1.0)
        finally:
            kernel32.CloseHandle(handle)
    else:
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except ProcessLookupError:
                break
            except OSError:
                time.sleep(0.2)


def log_error(message: str) -> None:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    log_path = os.path.join(appdata, "UniversalRecoilMenu", "updater.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def apply_update(
    staged_exe: str,
    target_exe: str,
    expected_sha256: str = "",
    pid: int = 0,
    restart: bool = True,
) -> None:
    wait_for_process_exit(pid, timeout=25.0)
    time.sleep(0.4)

    if not is_valid_pe(staged_exe):
        raise RuntimeError("Staged update file is missing or not a valid Windows executable.")

    expected_norm = (expected_sha256 or "").strip().lower()
    if expected_norm:
        actual_sha = sha256_file(staged_exe)
        if actual_sha != expected_norm:
            raise RuntimeError(f"SHA-256 mismatch: expected {expected_norm}, got {actual_sha}")

    target_abs = os.path.abspath(target_exe)
    target_dir = os.path.dirname(target_abs)
    os.makedirs(target_dir, exist_ok=True)

    backup_exe = target_abs + ".old"
    new_exe = target_abs + ".new"

    shutil.copy2(staged_exe, new_exe)
    if not is_valid_pe(new_exe):
        try:
            os.remove(new_exe)
        except OSError:
            pass
        raise RuntimeError("Copied update binary failed validation.")

    moved_old = False
    try:
        if os.path.exists(target_abs):
            if os.path.exists(backup_exe):
                try:
                    os.remove(backup_exe)
                except OSError:
                    pass
            os.replace(target_abs, backup_exe)
            moved_old = True

        os.replace(new_exe, target_abs)

        if moved_old and os.path.exists(backup_exe):
            try:
                os.remove(backup_exe)
            except OSError:
                pass
    except Exception as exc:
        if moved_old and os.path.exists(backup_exe) and not os.path.exists(target_abs):
            try:
                os.replace(backup_exe, target_abs)
            except OSError:
                pass
        if os.path.exists(new_exe):
            try:
                os.remove(new_exe)
            except OSError:
                pass
        raise RuntimeError(f"Failed to replace executable: {exc}") from exc

    try:
        if os.path.exists(staged_exe):
            os.remove(staged_exe)
    except OSError:
        pass

    if restart:
        flags = 0
        if os.name == "nt" and hasattr(subprocess, "DETACHED_PROCESS"):
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([target_abs], cwd=target_dir, close_fds=True, creationflags=flags)


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone EXE Updater")
    parser.add_argument("--staged", required=True, help="Path to downloaded update .exe")
    parser.add_argument("--target", required=True, help="Path to target application .exe")
    parser.add_argument("--sha256", default="", help="Expected SHA-256 hex digest")
    parser.add_argument("--pid", type=int, default=0, help="PID of running app to wait for")
    parser.add_argument("--no-restart", action="store_true", help="Do not relaunch after swap")
    args = parser.parse_args()

    try:
        apply_update(
            staged_exe=args.staged,
            target_exe=args.target,
            expected_sha256=args.sha256,
            pid=args.pid,
            restart=not args.no_restart,
        )
        return 0
    except Exception as exc:
        log_error(str(exc))
        if os.name == "nt":
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"Update failed:\n{exc}\n\nYour settings and configs in AppData were not touched.",
                    "Updater Error",
                    0x10,
                )
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
