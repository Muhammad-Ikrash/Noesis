@echo off
setlocal
title Noesis launcher
cd /d "%~dp0"

echo.
echo  ==== Noesis ====
echo.

rem ---- Prerequisites -------------------------------------------------------
where docker >nul 2>&1 || (echo [x] Docker is not installed or not on PATH. & goto :fail)
where uv >nul 2>&1     || (echo [x] uv is not installed. See https://docs.astral.sh/uv/ & goto :fail)
where npm >nul 2>&1    || (echo [x] Node.js / npm is not installed. & goto :fail)

rem ---- Docker engine (starts Docker Desktop if it isn't running) ----------
docker info >nul 2>&1
if not errorlevel 1 goto :dockerready

set "DOCKER_EXE="
for %%P in ("%ProgramFiles%\Docker\Docker\Docker Desktop.exe" "%LOCALAPPDATA%\Programs\Docker\Docker\Docker Desktop.exe" "%LOCALAPPDATA%\Docker\Docker Desktop.exe") do (
  if not defined DOCKER_EXE if exist %%P set "DOCKER_EXE=%%~P"
)
if not defined DOCKER_EXE (
  echo [x] Docker is not running and Docker Desktop could not be found. Start it manually, then run this again.
  goto :fail
)

echo [0/4] Starting Docker Desktop, this can take a minute...
start "" "%DOCKER_EXE%"
set /a tries=0
:waitdocker
"%SystemRoot%\System32\timeout.exe" /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto :dockerready
set /a tries+=1
if %tries% geq 60 (
  echo [x] Docker Desktop did not become ready within 3 minutes. Check its window, then run this again.
  goto :fail
)
goto :waitdocker
:dockerready
echo       Docker is running.

if not exist "Backend\.env" (
  copy "Backend\.env.example" "Backend\.env" >nul
  echo [!] Created Backend\.env from .env.example.
  echo     Set LLM_API_KEY in it, save, then run this file again.
  start "" notepad "Backend\.env"
  goto :fail
)

rem ---- Database ------------------------------------------------------------
echo [1/4] Starting the database container...
pushd Backend
docker compose up -d db || (popd & echo [x] Could not start the database. & goto :fail)

echo       Waiting for Postgres to accept connections...
set /a tries=0
:waitdb
docker compose exec -T db pg_isready -U noesis >nul 2>&1
if not errorlevel 1 goto :dbready
set /a tries+=1
if %tries% geq 30 (popd & echo [x] Postgres did not become ready in time. & goto :fail)
"%SystemRoot%\System32\timeout.exe" /t 2 /nobreak >nul
goto :waitdb
:dbready
popd

rem ---- Backend -------------------------------------------------------------
echo [2/4] Starting the backend (migrations, then http://127.0.0.1:8000)...
start "Noesis backend" /d "%~dp0Backend" cmd /k "uv sync && uv run alembic upgrade head && uv run backend"

rem ---- Frontend ------------------------------------------------------------
echo [3/4] Starting the frontend (http://localhost:4200)...
if not exist "Frontend\Noesis\node_modules" (
  echo       Installing frontend packages, first run only...
  pushd Frontend\Noesis
  call npm ci || (popd & echo [x] npm ci failed. & goto :fail)
  popd
)
start "Noesis frontend" /d "%~dp0Frontend\Noesis" cmd /k "npm start"

rem ---- Browser -------------------------------------------------------------
echo [4/4] Waiting for the app to come up...
set /a tries=0
:waitweb
curl -s -o nul http://localhost:4200 >nul 2>&1
if not errorlevel 1 goto :open
set /a tries+=1
if %tries% geq 90 goto :open
"%SystemRoot%\System32\timeout.exe" /t 2 /nobreak >nul
goto :waitweb
:open
start "" http://localhost:4200

echo.
echo  Noesis is running. Close the "Noesis backend" and "Noesis frontend"
echo  windows to stop it. The database keeps running in Docker; stop it with:
echo      docker compose -f Backend\docker-compose.yml stop db
echo.
"%SystemRoot%\System32\timeout.exe" /t 8 >nul
exit /b 0

:fail
echo.
pause
exit /b 1
