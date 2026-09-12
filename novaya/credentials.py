"""The API key: where it lives, and how it is proved to persist.

Stored means A SEPARATE PROCESS CAN READ IT BACK. A shell export satisfies
anything weaker and dies with the shell, which is how setup used to report
success and leave the next session unable to authenticate.

Precedence: NOVGRAPH_API_KEY (deliberate) > store > CODEWIKI_API_KEY (ambient,
often stale). The key is never written to a repo, a .md, an adapter config or
a log -- only the non-secret loader identifier is.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVICE = "novaya-novgraph"
ACCOUNT = "context-api"

ENV_EXPLICIT = "NOVGRAPH_API_KEY"
ENV_AMBIENT = "CODEWIKI_API_KEY"

_WINDOWS = sys.platform.startswith("win")
_MACOS = sys.platform == "darwin"


def _home_dir() -> Path:
    """Per-user state directory, outside any repository."""
    if _WINDOWS:
        root = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(root) / "Novaya" / "novgraph"
    root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "novaya" / "novgraph"


def _file_path() -> Path:
    return _home_dir() / ("key.dpapi" if _WINDOWS else "key")


def _run(argv, stdin_text="", timeout=20.0, env=None):
    """Run a helper without ever putting a secret in argv where we can help it."""
    try:
        return subprocess.run(
            argv, input=stdin_text, capture_output=True, text=True,
            timeout=timeout, check=False,
            env=({**os.environ, **env} if env else None),
        )
    except (OSError, subprocess.SubprocessError):
        return None


# -- Windows: DPAPI. Secret on STDIN: command lines are world-readable. -------

_PS_STORE = (
    "$ErrorActionPreference = 'Stop';"
    "$k = [Console]::In.ReadToEnd().Trim();"
    "if (-not $k) { exit 3 };"
    "$target = $env:NOVGRAPH_KEY_PATH;"
    "$dir = Split-Path -Parent $target;"
    "if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null };"
    "ConvertTo-SecureString -String $k -AsPlainText -Force | ConvertFrom-SecureString | "
    "Set-Content -Path $target -Encoding ascii"
)

_PS_LOAD = (
    "$ErrorActionPreference = 'Stop';"
    "$target = $env:NOVGRAPH_KEY_PATH;"
    "if (-not (Test-Path $target)) { exit 4 };"
    "[Runtime.InteropServices.Marshal]::PtrToStringBSTR("
    "[Runtime.InteropServices.Marshal]::SecureStringToBSTR("
    "(Get-Content $target | ConvertTo-SecureString)))"
)


def _powershell(script, path, stdin_text=""):
    # Path via env, not argv: `powershell -Command` appends trailing args to
    # the command text instead of binding $args, so $target read empty.
    return _run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        stdin_text=stdin_text,
        env={"NOVGRAPH_KEY_PATH": str(path)},
    )


def _dpapi_store(key: str) -> bool:
    path = _file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    res = _powershell(_PS_STORE, path, stdin_text=key)
    return bool(res and res.returncode == 0 and path.exists())


def _dpapi_load() -> str:
    path = _file_path()
    if not path.exists():
        return ""
    res = _powershell(_PS_LOAD, path)
    if not res or res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


# -- macOS: Keychain ----------------------------------------------------------

def _keychain_store(key: str) -> bool:
    # `security` has no stdin form; the secret is in argv for one exec.
    res = _run(["security", "add-generic-password", "-U",
                "-s", SERVICE, "-a", ACCOUNT, "-w", key])
    return bool(res and res.returncode == 0)


def _keychain_load() -> str:
    res = _run(["security", "find-generic-password",
                "-s", SERVICE, "-a", ACCOUNT, "-w"])
    if not res or res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


def _keychain_clear() -> bool:
    res = _run(["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT])
    return bool(res and res.returncode == 0)


# -- Linux: libsecret ---------------------------------------------------------

def _secret_tool_store(key: str) -> bool:
    res = _run(["secret-tool", "store", "--label=Novaya Novayagraph",
                "service", SERVICE, "account", ACCOUNT], stdin_text=key)
    return bool(res and res.returncode == 0)


def _secret_tool_load() -> str:
    res = _run(["secret-tool", "lookup", "service", SERVICE, "account", ACCOUNT])
    if not res or res.returncode != 0:
        return ""
    return (res.stdout or "").strip()


def _secret_tool_clear() -> bool:
    res = _run(["secret-tool", "clear", "service", SERVICE, "account", ACCOUNT])
    return bool(res and res.returncode == 0)


# -- everywhere: a 0600 file --------------------------------------------------

def _plain_path() -> Path:
    """The plaintext fallback. Never the .dpapi name: a bare key in a file
    called key.dpapi reads as encrypted to whoever finds it."""
    return _home_dir() / "key"


def _file_store(key: str) -> bool:
    path = _plain_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key.strip() + "\n", encoding="utf-8")
        if not _WINDOWS:
            os.chmod(path, 0o600)
        return True
    except OSError:
        return False


def _file_load() -> str:
    try:
        return _plain_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _file_clear() -> bool:
    try:
        _plain_path().unlink()
        return True
    except OSError:
        return False


# -- the interface the rest of the client uses --------------------------------

def preferred_backend() -> str:
    if _WINDOWS:
        return "dpapi"
    if _MACOS:
        return "keychain"
    if _run(["secret-tool", "--version"]) is not None:
        return "secret-tool"
    return "file"


def loader_hint(backend: str) -> str:
    """A NON-SECRET description of where the key is, safe to write into a repo."""
    if backend == "dpapi":
        return "Windows DPAPI, current user only: " + str(_file_path())
    if backend == "keychain":
        return "macOS Keychain: service " + SERVICE + ", account " + ACCOUNT
    if backend == "secret-tool":
        return "libsecret: service " + SERVICE + ", account " + ACCOUNT
    return "file, mode 0600: " + str(_plain_path())


def store(key: str) -> dict:
    """Persist the key. Falls back to a file rather than failing outright."""
    key = (key or "").strip()
    if not key:
        raise ValueError("empty key")
    backend = preferred_backend()
    ok = False
    if backend == "dpapi":
        ok = _dpapi_store(key)
    elif backend == "keychain":
        ok = _keychain_store(key)
    elif backend == "secret-tool":
        ok = _secret_tool_store(key)
    elif backend == "file":
        ok = _file_store(key)
    if not ok:
        # Degrade, never fail: adapters must not be wired to a missing key.
        ok = _file_store(key)
        backend = "file" if ok else "none"
    if not ok:
        raise OSError("could not persist the key in any credential store")
    return {"backend": backend, "loader": loader_hint(backend)}


def load_stored() -> str:
    """Read the key back from the credential store only -- no environment."""
    readers = []
    if _WINDOWS:
        readers.append(_dpapi_load)
    elif _MACOS:
        readers.append(_keychain_load)
    else:
        readers.append(_secret_tool_load)
    readers.append(_file_load)
    for reader in readers:
        value = reader()
        if value:
            return value
    return ""


def load() -> str:
    """The key this process should use, by the precedence rule above."""
    explicit = (os.environ.get(ENV_EXPLICIT) or "").strip()
    if explicit:
        return explicit
    stored = load_stored()
    if stored:
        return stored
    return (os.environ.get(ENV_AMBIENT) or "").strip()


def source() -> str:
    """Which of the three won, for `doctor` to report. Never the value."""
    if (os.environ.get(ENV_EXPLICIT) or "").strip():
        return ENV_EXPLICIT
    if load_stored():
        return "credential store (" + preferred_backend() + ")"
    if (os.environ.get(ENV_AMBIENT) or "").strip():
        return ENV_AMBIENT + " (inherited environment -- not persistent)"
    return ""


def clear():
    """Remove the stored key from every backend that has one."""
    gone = []
    if _WINDOWS and _file_path().exists():
        try:
            _file_path().unlink()
            gone.append("dpapi")
        except OSError:
            pass
    if _MACOS and _keychain_clear():
        gone.append("keychain")
    if not (_WINDOWS or _MACOS) and _secret_tool_clear():
        gone.append("secret-tool")
    if _plain_path().exists() and _file_clear():
        gone.append("file")
    return gone


def verify_separate_process() -> bool:
    """Can a DIFFERENT process read this key back? The one check a shell
    export fails, so install runs it rather than leaving it to next session."""
    package_parent = str(Path(__file__).resolve().parent.parent)
    code = ("import sys; sys.path.insert(0, %r); "
            "from novaya import credentials; "
            "sys.exit(0 if credentials.load_stored() else 5)" % package_parent)
    env = dict(os.environ)
    env.pop(ENV_EXPLICIT, None)
    env.pop(ENV_AMBIENT, None)
    try:
        res = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=60, env=env, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0
