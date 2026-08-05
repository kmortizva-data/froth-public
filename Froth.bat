@echo off
rem Froth launcher - double-click to start the app (the browser opens by itself).
rem Close this window (or Ctrl+C) to stop the app.
rem It first kills any LEFTOVER Froth server, so you never attach to a stale one
rem (a zombie server keeps OLD code in memory and "loads suspiciously fast").
cd /d "%~dp0"
for %%P in (8501 8502 8503) do (
  for /f "tokens=5" %%p in ('netstat -ano ^| findstr LISTENING ^| findstr :%%P') do (
    taskkill /F /PID %%p >nul 2>&1
  )
)
.venv\Scripts\python.exe -m streamlit run app.py
pause
