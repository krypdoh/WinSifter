@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  WinSifter — Build standalone .exe
REM  Requires:  pip install pyinstaller customtkinter
REM  Output:    dist\WinSifter.exe
REM ─────────────────────────────────────────────────────────────────────────────

echo Building WinSifter.exe with PyInstaller...

pyinstaller ^
  --onefile ^
  --windowed ^
  --name WinSifter ^
  --collect-data customtkinter ^
  winsifter.py

echo.
if exist dist\WinSifter.exe (
    echo  Build complete:  dist\WinSifter.exe
) else (
    echo  Build FAILED — check output above for errors.
)
pause
