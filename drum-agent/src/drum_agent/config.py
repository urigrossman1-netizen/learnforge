"""Paths, .env loading and tool discovery shared by every command."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_DIR / ".env"
AUDIO_DIR = PROJECT_DIR / "audio"
CHARTS_DIR = PROJECT_DIR / "charts"
CACHE_DIR = PROJECT_DIR / ".cache"

# Pinned versions of the third-party MCP servers (see .mcp.json).
YOUTUBE_MCP_PACKAGE = "@kevinwatt/yt-dlp-mcp@0.10.0"
SPOTIFY_MCP_PACKAGE = "mcp-server-spotify@0.3.0"
# mcp-server-spotify 0.3.0 imports FastMCP, which MCP Python SDK 2.x renamed.
SPOTIFY_MCP_CONSTRAINT = "mcp[cli]>=1.29,<2"


def _parse_env_value(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()  # drop an inline comment


def load_env(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE lines from .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = _parse_env_value(value)
        if value:
            os.environ.setdefault(key.strip(), value)


def write_env(updates: dict[str, str], path: Path = ENV_FILE) -> None:
    """Merge updates into .env, keeping unrelated lines, and restrict permissions."""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in remaining.items())
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def venv_bin() -> Path:
    """Directory holding this environment's executables (yt-dlp, deno)."""
    return Path(sys.executable).parent


def which(name: str) -> str | None:
    """Find an executable, preferring this project's virtualenv."""
    return shutil.which(name, path=str(venv_bin())) or shutil.which(name)


def ffmpeg_exe() -> str:
    """System ffmpeg if installed, otherwise the static build shipped by imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def tool_path() -> str:
    """PATH with the venv first and an `ffmpeg` shim when only the bundled build exists.

    Child processes (yt-dlp, the MCP servers) look tools up by name, so they
    need to see the same yt-dlp/deno/ffmpeg this package uses.
    """
    parts = [str(venv_bin())]
    if not shutil.which("ffmpeg"):
        shim_dir = CACHE_DIR / "bin"
        shim = shim_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if not shim.exists():  # also true for a dangling link left by an old venv
            shim_dir.mkdir(parents=True, exist_ok=True)
            src = ffmpeg_exe()
            # Build under a unique name and rename into place, so two servers
            # starting at once cannot trip over a half-made shim.
            tmp = shim_dir / f".{shim.name}.{os.getpid()}.tmp"
            try:
                tmp.unlink(missing_ok=True)
                try:
                    tmp.symlink_to(src)
                except OSError:
                    shutil.copy2(src, tmp)
                os.replace(tmp, shim)
            except OSError:
                if not shim.exists():
                    raise
        parts.append(str(shim_dir))
    parts.append(os.environ.get("PATH", ""))
    return os.pathsep.join(parts)


def slugify(text: str, max_len: int = 80) -> str:
    """ASCII file name for a song. Non-Latin titles get a short stable hash so
    two different songs never share a slug (e.g. two Cyrillic titles)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()[:max_len].strip("-")
    if any(ch.isalnum() and not ch.isascii() for ch in unicodedata.normalize("NFKD", text)):
        digest = hashlib.sha1(unicodedata.normalize("NFC", text).encode()).hexdigest()[:8]
        slug = f"{slug or 'song'}-{digest}"
    return slug or "song"


BROWSERS = ("brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale")


def cookies_from_browser() -> tuple | None:
    """DRUM_AGENT_COOKIES_FROM_BROWSER parsed like yt-dlp's --cookies-from-browser:
    BROWSER[+KEYRING][:PROFILE][::CONTAINER], returned as yt-dlp's API tuple."""
    spec = os.environ.get("DRUM_AGENT_COOKIES_FROM_BROWSER", "").strip()
    if not spec or spec.lower() == "none":
        return None
    m = re.fullmatch(
        r"(?P<name>[^+:]+)(?:\s*\+\s*(?P<keyring>[^:]+))?(?:\s*:\s*(?!:)(?P<profile>.+?))?(?:\s*::\s*(?P<container>.+))?",
        spec,
    )
    if not m or m["name"].strip().lower() not in BROWSERS:
        raise ValueError(
            f"DRUM_AGENT_COOKIES_FROM_BROWSER={spec!r}: use one of {', '.join(BROWSERS)} "
            "(optionally browser:profile). Fix it with `uv run drum-agent setup --cookies-from-browser firefox`."
        )
    keyring = m["keyring"].strip().upper() if m["keyring"] else None
    return (m["name"].strip().lower(), m["profile"], keyring, m["container"])
