"""Launcher: starts the FastAPI backend with Chainlit UI mounted.

Automatically uses the ``.venv`` virtual environment.  If it doesn't
exist yet, the script creates it and installs dependencies first.

Usage::

    python run.py           # start the app
    python run.py --test    # run the test suite instead

Press Ctrl+C to stop the backend.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VENV_DIR = _ROOT / ".venv"

# Platform-aware paths inside the venv.
_IS_WINDOWS = sys.platform == "win32"
if _IS_WINDOWS:
    _VENV_PYTHON = _VENV_DIR / "Scripts" / "python.exe"
    _VENV_PIP = _VENV_DIR / "Scripts" / "pip.exe"
else:
    _VENV_PYTHON = _VENV_DIR / "bin" / "python"
    _VENV_PIP = _VENV_DIR / "bin" / "pip"

_REQUIREMENTS = _ROOT / "requirements.txt"


# ── Virtual environment bootstrap ────────────────────────────────────────

def _ensure_venv() -> None:
    """Create the venv and install dependencies if it doesn't exist."""
    if _VENV_PYTHON.exists():
        return  # Already set up.

    print("[run] Virtual environment not found. Creating .venv ...")
    subprocess.check_call([sys.executable, "-m", "venv", str(_VENV_DIR)])

    print("[run] Upgrading pip ...")
    subprocess.check_call(
        [str(_VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
    )

    print(f"[run] Installing dependencies from {_REQUIREMENTS.name} ...")
    subprocess.check_call(
        [str(_VENV_PIP), "install", "-r", str(_REQUIREMENTS)],
    )

    print("[run] Installing dev dependencies (pytest) ...")
    subprocess.check_call(
        [str(_VENV_PIP), "install", "pytest"],
    )

    print("[run] Virtual environment ready.\n")


# ── Load .env (using stdlib only — no dotenv import at top level) ────────

def _load_env_file() -> None:
    """Minimal .env loader so we don't need dotenv installed globally."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Don't overwrite already-set env vars.
        if key not in os.environ:
            os.environ[key] = value


# ── Main ─────────────────────────────────────────────────────────────────

def _run_tests() -> None:
    """Run the test suite using the venv's pytest."""
    _ensure_venv()
    if _IS_WINDOWS:
        venv_pytest = _VENV_DIR / "Scripts" / "pytest.exe"
    else:
        venv_pytest = _VENV_DIR / "bin" / "pytest"
    cmd = [str(venv_pytest), "tests/", "-v"]
    print(f"[run] Running tests: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(_ROOT))
    sys.exit(result.returncode)


def main() -> None:
    _ensure_venv()
    _load_env_file()

    # Read config from env.
    backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port = os.getenv("BACKEND_PORT", "8000")
    workers = os.getenv("WORKERS", "4")
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    # All subprocesses use the venv Python.
    venv_py = str(_VENV_PYTHON)

    procs: list[subprocess.Popen] = []

    try:
        # ── Start FastAPI backend ────────────────────────────────────
        backend_cmd = [
            venv_py, "-m", "uvicorn",
            "backend.main:app",
            "--host", backend_host,
            "--port", backend_port,
            "--workers", workers,
            "--log-level", log_level,
        ]
        print(f"[run] Starting backend: {' '.join(backend_cmd)}")
        backend = subprocess.Popen(backend_cmd, cwd=str(_ROOT))
        procs.append(backend)

        print(f"\n[run] Backend with Chainlit UI -> http://{backend_host}:{backend_port}/")
        print(f"[run] Health check -> http://{backend_host}:{backend_port}/api/v1/health")
        print(f"[run] API docs -> http://{backend_host}:{backend_port}/docs")
        print("[run] Press Ctrl+C to stop.\n")

        # Wait for the backend process to exit.
        while True:
            ret = backend.poll()
            if ret is not None:
                print(f"[run] Backend process {backend.pid} exited with code {ret}.")
                raise SystemExit(ret)
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        print("\n[run] Shutting down...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("[run] All processes stopped.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        main()
