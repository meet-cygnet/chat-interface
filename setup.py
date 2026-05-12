"""One-time setup: creates a virtual environment and installs dependencies.

Usage::

    python setup.py
"""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VENV_DIR = _ROOT / ".venv"
_REQUIREMENTS = _ROOT / "requirements.txt"

# Platform-aware paths inside the venv.
_IS_WINDOWS = sys.platform == "win32"
if _IS_WINDOWS:
    _VENV_PYTHON = _VENV_DIR / "Scripts" / "python.exe"
    _VENV_PIP = _VENV_DIR / "Scripts" / "pip.exe"
else:
    _VENV_PYTHON = _VENV_DIR / "bin" / "python"
    _VENV_PIP = _VENV_DIR / "bin" / "pip"


def main() -> None:
    # ── 1. Create venv ───────────────────────────────────────────────
    if not _VENV_DIR.exists():
        print(f"[setup] Creating virtual environment in {_VENV_DIR} ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(_VENV_DIR)])
        print("[setup] Virtual environment created.")
    else:
        print(f"[setup] Virtual environment already exists at {_VENV_DIR}")

    # ── 2. Upgrade pip ───────────────────────────────────────────────
    print("[setup] Upgrading pip ...")
    subprocess.check_call(
        [str(_VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
    )

    # ── 3. Install requirements ──────────────────────────────────────
    print(f"[setup] Installing dependencies from {_REQUIREMENTS.name} ...")
    subprocess.check_call(
        [str(_VENV_PIP), "install", "-r", str(_REQUIREMENTS)],
    )

    # ── 4. Install dev/test dependencies ─────────────────────────────
    print("[setup] Installing dev dependencies (pytest) ...")
    subprocess.check_call(
        [str(_VENV_PIP), "install", "pytest"],
    )

    print()
    print("=" * 60)
    print("  Setup complete!")
    print(f"  venv: {_VENV_DIR}")
    print(f"  python: {_VENV_PYTHON}")
    print()
    print("  To run the app:")
    print("    python run.py")
    print()
    print("  To run tests:")
    print("    python run.py --test")
    print("=" * 60)


if __name__ == "__main__":
    main()
