@echo off
rem Froth as a desktop app: its own window, no browser (Spotify-style).
rem Closing the window also stops the engine.
rem Kills any LEFTOVER Froth server first - desktop.py reuses a running server if it
rem finds one, which silently serves OLD code after an update (the zombie trap).
cd /d "%~dp0"
for %%P in (8501 8502 8503) do (
  for /f "tokens=5" %%p in ('netstat -ano ^| findstr LISTENING ^| findstr :%%P') do (
    taskkill /F /PID %%p >nul 2>&1
  )
)
start "" ".venv\Scripts\pythonw.exe" desktop.py
