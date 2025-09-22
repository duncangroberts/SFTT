@echo off
setlocal
REM Launch the Tkinter app without a console window if possible.
REM Double-click this file to run the app.

pushd %~dp0

REM Try pythonw.exe first (no console). Falls back to python.exe if needed.
where pythonw >NUL 2>NUL
if %ERRORLEVEL%==0 (
    pythonw.exe main.py
) else (
    echo pythonw.exe not found on PATH. Trying python.exe...
    python.exe main.py
)

popd

endlocal
