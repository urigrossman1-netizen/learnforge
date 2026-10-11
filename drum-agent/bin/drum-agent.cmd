@echo off
rem drum-agent launcher for Windows (cmd / PowerShell): runs the toolkit from this folder with uv.
where uv >nul 2>nul || (echo drum-agent needs uv: powershell -c "irm https://astral.sh/uv/install.ps1 | iex" 1>&2 & exit /b 127)
uv run --quiet --frozen --project "%~dp0.." drum-agent %*
