@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto no_python
  set "PY=python"
)

%PY% --version >nul 2>nul
if errorlevel 1 goto no_python

%PY% -c "import pymupdf; from PIL import Image" >nul 2>nul
if errorlevel 1 (
  echo Installing the required packages. This is needed only the first time and requires internet access.
  %PY% -m pip install --user -r requirements.txt
  if errorlevel 1 goto install_failed
)

%PY% app.py
if errorlevel 1 pause
goto end

:no_python
echo Python 3.10 or newer was not found.
echo Install Python 3 from python.org, enable the Python launcher or Add Python to PATH, then run this file again.
pause
goto end

:install_failed
echo Could not install the required packages. Check your internet connection and try again.
pause

goto end

:end
endlocal
