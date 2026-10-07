"""Launch the third-party MCP servers, and a minimal stdio client to test them.

This module does not implement an MCP server. `launch` only prepares the
environment (credentials from .env, the project's yt-dlp/deno/ffmpeg on PATH)
and execs the maintained packages pinned in config:

  youtube -> npx @kevinwatt/yt-dlp-mcp  (keyless; YouTube search, metadata, audio)
  spotify -> uvx mcp-server-spotify     (Spotify Web API, Feb-2026 compliant)
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import config


def server_command(name: str) -> list[str]:
    if name == "youtube":
        npx = shutil.which("npx")
        if npx and _node_major() >= 18:
            return [npx, "-y", config.YOUTUBE_MCP_PACKAGE]
        # No (recent) Node.js: deno, a project dependency, runs npm packages too.
        return [config.which("deno") or "deno", "run", "-A", f"npm:{config.YOUTUBE_MCP_PACKAGE}"]
    if name == "spotify":
        uv = os.environ.get("UV") or shutil.which("uv")
        pin = ["--with", config.SPOTIFY_MCP_CONSTRAINT, config.SPOTIFY_MCP_PACKAGE]
        if uv:
            return [uv, "tool", "run", *pin]
        return [shutil.which("uvx") or "uvx", *pin]
    raise ValueError(f"unknown MCP server {name!r} (expected youtube or spotify)")


def _node_major() -> int:
    node = shutil.which("node")
    if not node:
        return 0
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().lstrip("v").split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def server_env(name: str) -> dict[str, str]:
    config.load_env()
    env = dict(os.environ)
    env["PATH"] = config.tool_path()
    if name == "youtube":
        env.setdefault("YTDLP_DOWNLOADS_DIR", str(config.AUDIO_DIR / "youtube-mcp"))
        Path(env["YTDLP_DOWNLOADS_DIR"]).mkdir(parents=True, exist_ok=True)  # server refuses to start otherwise
        if env.get("DRUM_AGENT_COOKIES_FROM_BROWSER"):
            env.setdefault("YTDLP_COOKIES_FROM_BROWSER", env["DRUM_AGENT_COOKIES_FROM_BROWSER"])
    return env


def launch(name: str) -> int:
    """Replace this process with the MCP server (stdio passes straight through)."""
    cmd = server_command(name)
    env = server_env(name)
    if name == "spotify" and not (env.get("SPOTIFY_CLIENT_ID") and env.get("SPOTIFY_CLIENT_SECRET")):
        print(
            "spotify MCP: SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET missing. "
            "Run `uv run drum-agent setup` in drum-agent/.",
            file=sys.stderr,
        )
        return 1
    if os.name == "nt":
        return subprocess.call(cmd, env=env)
    os.execvpe(cmd[0], cmd, env)
    return 0  # unreachable


class StdioClient:
    """Just enough MCP (JSON-RPC over newline-delimited stdio) for `doctor`."""

    def __init__(self, cmd: list[str], cwd: Path, env: dict | None = None):
        self.proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._lines: queue.Queue = queue.Queue()
        self._stderr: list[str] = []
        threading.Thread(target=self._pump, args=(self.proc.stdout, self._lines), daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()
        self._id = 0

    def _pump(self, stream, q):
        for line in stream:
            q.put(line)
        q.put(None)

    def _drain(self):
        for line in self.proc.stderr:
            self._stderr.append(line)

    def request(self, method: str, params: dict | None = None, timeout: float = 60) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty:
                raise TimeoutError(f"no reply to {method} within {timeout:.0f}s") from None
            if line is None:
                raise RuntimeError("server exited: " + "".join(self._stderr)[-600:].strip())
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue
            if reply.get("id") == self._id:
                if "error" in reply:
                    raise RuntimeError(reply["error"].get("message", str(reply["error"])))
                return reply.get("result", {})

    def notify(self, method: str) -> None:
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def initialize(self, timeout: float = 180) -> dict:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "drum-agent-doctor", "version": "0.1"},
            },
            timeout=timeout,
        )
        self.notify("notifications/initialized")
        return result

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def project_server(name: str) -> tuple[list[str], Path]:
    """The command Claude Code runs for `name`, read from .mcp.json."""
    spec = json.loads((config.PROJECT_DIR / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][name]
    cmd = [spec["command"], *spec.get("args", [])]
    exe = shutil.which(cmd[0])
    if exe:
        cmd[0] = exe
    return cmd, config.PROJECT_DIR
