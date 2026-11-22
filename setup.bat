@echo off
setlocal EnableExtensions
title Noesis setup
cd /d "%~dp0"

echo.
echo  ==== Noesis setup ====
echo  Downloads everything Noesis needs. Safe to run again at any time.
echo.

set "INSTALLED_TOOL="

rem ---- 1. Tools: uv, Node.js, Docker Desktop (offered through winget) -----
echo [1/6] Checking tools...
call :need_tool uv "uv, the Python manager" astral-sh.uv
call :need_tool npm "Node.js LTS" OpenJS.NodeJS.LTS
call :need_tool docker "Docker Desktop" Docker.DockerDesktop
if defined MISSING_TOOL goto :fail
if defined INSTALLED_TOOL (
  echo.
  echo [!] New tools were installed. Close this window and run setup.bat again
  echo     so Windows picks them up. Docker Desktop may also ask you to sign out or restart.
  goto :fail
)
echo       uv, Node.js and Docker are installed.

rem ---- 2. Backend settings ---------------------------------------------------
echo [2/6] Backend settings...
if not exist "Backend\.env" (
  copy "Backend\.env.example" "Backend\.env" >nul
  echo       Created Backend\.env from .env.example.
)
findstr /c:"LLM_API_KEY=your-groq-api-key" "Backend\.env" >nul 2>&1
if not errorlevel 1 (
  set "NEED_KEY=1"
  echo       [!] LLM_API_KEY is still the placeholder. Add your Groq key before running Noesis.
)

rem ---- 3. Python and backend packages ----------------------------------------
echo [3/6] Installing Python and backend packages, first run downloads a few GB...
pushd Backend
call :uv_sync
if errorlevel 1 (popd & goto :fail)
popd

rem ---- 4. Database: Docker image and tables ----------------------------------
echo [4/6] Preparing the database...
call :ensure_docker
if errorlevel 1 goto :fail
pushd Backend
docker compose pull db
if errorlevel 1 (popd & echo [x] Could not download the database image. & goto :fail)
docker compose up -d db
if errorlevel 1 (popd & echo [x] Could not start the database. & goto :fail)
set /a tries=0
:waitdb
docker compose exec -T db pg_isready -U noesis >nul 2>&1
if not errorlevel 1 goto :dbready
set /a tries+=1
if %tries% geq 30 (popd & echo [x] Postgres did not become ready in time. & goto :fail)
call :sleep 2
goto :waitdb
:dbready
uv run alembic upgrade head
if errorlevel 1 (popd & echo [x] Database migrations failed. & goto :fail)
popd

rem ---- 5. Frontend packages ----------------------------------------------------
echo [5/6] Installing frontend packages...
pushd Frontend\Noesis
rem A clean install the first time; afterwards only update what changed, so a running
rem dev server keeps its files.
if exist node_modules (call npm install --no-audit --no-fund) else (call npm ci --no-audit --no-fund)
if errorlevel 1 (popd & echo [x] Installing frontend packages failed. & goto :fail)
popd

rem ---- 6. Embedding model ------------------------------------------------------
echo [6/6] Downloading the embedding model, about 1.2 GB the first time...
pushd Backend
uv run python -c "from huggingface_hub import snapshot_download; from backend.core.config import get_settings; m = get_settings().embedding_model; snapshot_download(m); print('      Model ready:', m)"
if errorlevel 1 (popd & echo [x] Could not download the embedding model. Check your internet connection. & goto :fail)
popd

echo.
echo  Setup complete. Start Noesis with run-noesis.bat.
if defined NEED_KEY echo  Remember to set LLM_API_KEY in Backend\.env first.
echo.
pause
exit /b 0

:fail
echo.
echo  Setup did not finish. Fix the message above and run setup.bat again.
echo.
pause
exit /b 1


rem ===== Helpers ================================================================

rem :need_tool <command> "<name>" <winget id>
rem Offers to install a missing tool with winget.
:need_tool
where %~1 >nul 2>&1
if not errorlevel 1 exit /b 0
echo       %~2 is not installed.
where winget >nul 2>&1
if errorlevel 1 (
  echo       [x] Install %~2 yourself, then run setup.bat again.
  set "MISSING_TOOL=1"
  exit /b 0
)
choice /c YN /m "      Install %~2 now with winget"
if errorlevel 2 (
  echo       [x] %~2 is required. Install it, then run setup.bat again.
  set "MISSING_TOOL=1"
  exit /b 0
)
winget install --id %~3 -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo       [x] winget could not install %~2.
  set "MISSING_TOOL=1"
  exit /b 0
)
set "INSTALLED_TOOL=1"
exit /b 0

rem :sleep <seconds> - ping works even when input is redirected, unlike timeout.
:sleep
set /a "pings=%~1+1"
ping -n %pings% 127.0.0.1 >nul
exit /b 0

rem :ensure_docker - starts Docker Desktop if it is not running and waits for it.
:ensure_docker
docker info >nul 2>&1
if not errorlevel 1 exit /b 0
set "DOCKER_EXE="
for %%P in ("%ProgramFiles%\Docker\Docker\Docker Desktop.exe" "%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe" "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" "%LOCALAPPDATA%\Docker\Docker Desktop.exe") do (
  if not defined DOCKER_EXE if exist %%P set "DOCKER_EXE=%%~P"
)
rem Fall back to the install that owns docker.exe: <install>\resources\bin\docker.exe
if not defined DOCKER_EXE (
  for /f "delims=" %%D in ('where docker 2^>nul') do (
    if not defined DOCKER_EXE if exist "%%~dpD..\..\Docker Desktop.exe" set "DOCKER_EXE=%%~dpD..\..\Docker Desktop.exe"
  )
)
if not defined DOCKER_EXE (
  echo [x] Docker is not running and Docker Desktop could not be found. Start it, then run setup.bat again.
  exit /b 1
)
echo       Starting Docker Desktop, this can take a minute...
start "" "%DOCKER_EXE%"
set /a dtries=0
:waitdocker
call :sleep 3
docker info >nul 2>&1
if not errorlevel 1 exit /b 0
set /a dtries+=1
if %dtries% geq 60 (
  echo [x] Docker Desktop did not become ready within 3 minutes.
  exit /b 1
)
goto :waitdocker

rem :uv_sync - runs "uv sync" in the current folder. On some Windows machines uv
rem downloads Python but cannot create its version link, so the first sync fails
rem with "Missing expected target directory for Python minor version link".
rem The interpreter itself is fine, so retry once and point uv at it directly.
:uv_sync
uv sync
if not errorlevel 1 exit /b 0
set "UV_PY="
for /d %%D in ("%APPDATA%\uv\python\cpython-3.13*") do (
  if exist "%%~D\python.exe" set "UV_PY=%%~D\python.exe"
)
if not defined UV_PY (
  echo [x] uv sync failed. See the message above.
  exit /b 1
)
echo       Retrying with the downloaded Python at %UV_PY%
uv sync --python "%UV_PY%"
if errorlevel 1 (
  echo [x] uv sync failed. See the message above.
  exit /b 1
)
exit /b 0
