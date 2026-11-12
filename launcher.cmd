@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem SPDX-License-Identifier: Apache-2.0
rem Native Windows launcher for twrpdtgen-NEXT.

set "ROOT_DIR=%~dp0"
set "CALLER_DIR=%CD%"
set "PYTHON_CMD="

call :find_python || exit /b 1
call :check_python || exit /b 1

if /I "%~1"=="--doctor" goto doctor
if /I "%~1"=="--self-test" goto self_test
if /I "%~1"=="--setup-only" goto setup_only

call :ensure_python_deps || exit /b 1

if "%~1"=="" goto ready

set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"
%PYTHON_CMD% -m twrpdtgen %*
set "RC=%ERRORLEVEL%"
exit /b %RC%

:find_python
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    exit /b 0
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)
echo [twrpdtgen-NEXT] ERROR: Python 3 was not found. 1>&2
echo Install Python 3.8 or newer and enable "Add Python to PATH". 1>&2
exit /b 1

:check_python
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [twrpdtgen-NEXT] ERROR: Python 3.8 or newer is required. 1>&2
    exit /b 1
)
exit /b 0

:ensure_python_deps
if "%TWRPDTGEN_SKIP_PIP%"=="1" exit /b 0
%PYTHON_CMD% -c "import git,jinja2,lz4,zstandard,sebaubuntu_libs" >nul 2>&1
if not errorlevel 1 exit /b 0
echo [twrpdtgen-NEXT] Installing Python dependencies from this clone...
%PYTHON_CMD% -m pip install -q -e "%ROOT_DIR%"
if errorlevel 1 (
    echo [twrpdtgen-NEXT] ERROR: Python dependency installation failed. 1>&2
    exit /b 1
)
exit /b 0

:doctor
call :ensure_python_deps || exit /b 1
set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"
%PYTHON_CMD% -c "import git,jinja2,lz4,zstandard,sebaubuntu_libs,twrpdtgen,sys; print('python:',sys.version.split()[0]); print('twrpdtgen-NEXT:',twrpdtgen.__version__)"
if errorlevel 1 exit /b 1
%PYTHON_CMD% -c "import os,tempfile,pathlib; p=pathlib.Path(tempfile.mkdtemp()); a=p/'a'; b=p/'b'; a.write_text('x'); ok=True; exec('try:\n b.symlink_to(a.name)\nexcept OSError:\n ok=False'); print('windows symlinks:', 'available' if ok else 'unavailable (Developer Mode/admin may be needed)')"
echo [twrpdtgen-NEXT] Environment check passed.
exit /b 0

:self_test
call :ensure_python_deps || exit /b 1
pushd "%ROOT_DIR%"
set "PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%"
%PYTHON_CMD% -m compileall -q twrpdtgen tests
if errorlevel 1 (popd & exit /b 1)
%PYTHON_CMD% -m unittest discover -s tests -v
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:setup_only
call :ensure_python_deps || exit /b 1
call :doctor || exit /b 1
goto ready

:ready
echo.
echo twrpdtgen-NEXT is ready for native Windows modern-image parsing.
echo.
echo General form:
echo   launcher.cmd [path-to-image-containing-recovery-ramdisk] -o [output-folder]
echo.
echo Example:
echo   launcher.cmd "C:\firmware\recovery.img" -o "C:\twrp\output"
echo.
echo Modern split layout:
echo   launcher.cmd "C:\firmware\init_boot.img" --boot-image "C:\firmware\boot.img" --vendor-boot "C:\firmware\vendor_boot.img" -o "C:\twrp\output"
echo.
echo The output folder is created automatically when it does not exist.
echo Modern boot/recovery v3/v4, init_boot v4 and vendor_boot v3/v4 use the native Python parser.
echo Older legacy AIK-only image formats can still require Linux/WSL host tooling.
echo.
echo Launcher commands:
echo   launcher.cmd --doctor
echo   launcher.cmd --self-test
echo   launcher.cmd --setup-only
exit /b 0
