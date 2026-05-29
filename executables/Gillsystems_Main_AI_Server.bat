@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0.."
set "LOG_DIR=%REPO_ROOT%\logs"
set "MODEL_PATH=C:\Models\gemma-4-31B.Q4_K_M.gguf"
set "NODE_PREFIX=gillsystems_cluster-main"
set "PUBLIC_HOST=10.0.0.164"
set "PUBLIC_PORT=8010"
set "UPSTREAM_HOST=127.0.0.1"
set "UPSTREAM_PORT=18010"
set "PROXY_SCRIPT=%REPO_ROOT%\scripts\llama_json_proxy.py"
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "PROXY_PID_FILE=%LOG_DIR%\%NODE_PREFIX%_proxy.pid"

if defined GILLSYSTEMS_MAIN_MODEL_PATH set "MODEL_PATH=%GILLSYSTEMS_MAIN_MODEL_PATH%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd_HH-mm-ss')"') do set "TIMESTAMP=%%I"
set "SERVER_LOG=%LOG_DIR%\server_%COMPUTERNAME%_%TIMESTAMP%.log"

echo Starting Gillsystems-Main LLM Server..LOCKED IN RADEON 7900XTX!
cd /d "C:\Gillsystems\llama.cpp\bin\"

if /I "%~1"=="--dry-run" (
  echo Binary:  C:\Gillsystems\llama.cpp\bin\llama-server.exe
  echo Model:   %MODEL_PATH%
  echo Host:    %PUBLIC_HOST%:%PUBLIC_PORT%
  echo Context: 49152
  echo Logs:    %LOG_DIR%
  echo.
  echo JSON Export Command:
  echo   "%PYTHON_EXE%" "%PROXY_SCRIPT%" --listen-host %PUBLIC_HOST% --listen-port %PUBLIC_PORT% --upstream-host %UPSTREAM_HOST% --upstream-port %UPSTREAM_PORT% --logs-dir "%LOG_DIR%" --node-prefix %NODE_PREFIX% --pid-file "%PROXY_PID_FILE%"
  echo.
  echo Launch Command:
  echo   llama-server.exe -m "%MODEL_PATH%" -c 49152 -n 2048 -ngl 99 -fa on -np 1 -b 2048 -ub 512 --port %UPSTREAM_PORT% --host %UPSTREAM_HOST% --temperature 1.0 --top-k 64 --top-p 0.95 --min-p 0.05 --reasoning-format none --jinja --chat-template gemma --context-shift --repeat-penalty 1.15 --repeat-last-n 128 --ui-config "{\"chatFormat\":\"auto\"}" --log-file "%SERVER_LOG%" --log-timestamps --metrics --no-mmap
  exit /b 0
)

if not exist "llama-server.exe" (
  echo [Gillsystems] ERROR: llama-server.exe not found at "C:\Gillsystems\llama.cpp\bin\llama-server.exe"
  pause
  exit /b 1
)

if not exist "%MODEL_PATH%" (
  echo [Gillsystems] ERROR: Model not found at "%MODEL_PATH%"
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [Gillsystems] ERROR: Python launcher not found at "%PYTHON_EXE%"
  pause
  exit /b 1
)

if not exist "%PROXY_SCRIPT%" (
  echo [Gillsystems] ERROR: JSON export proxy not found at "%PROXY_SCRIPT%"
  pause
  exit /b 1
)

if exist "%PROXY_PID_FILE%" (
  for /f %%I in (%PROXY_PID_FILE%) do taskkill /PID %%I /F >nul 2>&1
  del "%PROXY_PID_FILE%" >nul 2>&1
)

start "Gillsystems-Main JSON Export" /min "%COMSPEC%" /c ""%PYTHON_EXE%" "%PROXY_SCRIPT%" --listen-host %PUBLIC_HOST% --listen-port %PUBLIC_PORT% --upstream-host %UPSTREAM_HOST% --upstream-port %UPSTREAM_PORT% --logs-dir "%LOG_DIR%" --node-prefix %NODE_PREFIX% --pid-file "%PROXY_PID_FILE%""
timeout /t 2 /nobreak >nul

if not exist "%PROXY_PID_FILE%" (
  echo [Gillsystems] ERROR: JSON export proxy failed to start.
  pause
  exit /b 1
)

llama-server.exe ^
  -m "%MODEL_PATH%" ^
  -c 49152 ^
  -n 2048 ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  -b 2048 ^
  -ub 512 ^
  --port %UPSTREAM_PORT% ^
  --host %UPSTREAM_HOST% ^
  --temperature 1.0 ^
  --top-k 64 ^
  --top-p 0.95 ^
  --min-p 0.05 ^
  --reasoning-format none ^
  --jinja ^
  --chat-template gemma ^
  --context-shift ^
  --repeat-penalty 1.15 ^
  --repeat-last-n 128 ^
  --ui-config "{\"chatFormat\":\"auto\"}" ^
  --log-file "%SERVER_LOG%" ^
  --log-timestamps ^
  --metrics ^
  --no-mmap

set "EXIT_CODE=%ERRORLEVEL%"

if exist "%PROXY_PID_FILE%" (
  for /f %%I in (%PROXY_PID_FILE%) do taskkill /PID %%I /F >nul 2>&1
  del "%PROXY_PID_FILE%" >nul 2>&1
)

pause
exit /b %EXIT_CODE%