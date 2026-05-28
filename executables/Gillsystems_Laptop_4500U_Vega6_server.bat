@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo Starting Gillsystems-Laptop LLM Server... Tier 2 Edge Profile.

set "MODEL_PATH=C:\Users\Gillsystems Laptop\Desktop\Models\gemma-4-E4B.Q6_K.gguf"
set "HOST=10.0.0.93"
set "PORT=8012"
set "CTX_SIZE=32768"
set "N_PREDICT=1024"
set "GPU_LAYERS=99"
set "PARALLEL_REQUESTS=1"
set "FLASH_ATTN=on"
set "BATCH_SIZE=2048"
set "UBATCH_SIZE=512"
set "CHAT_TEMPLATE=gemma"
set "USE_HIP_UMA=1"

:: Gemma 4 model card baseline
set "TEMPERATURE=1.0"
set "TOP_K=64"
set "TOP_P=0.95"
set "REPEAT_PENALTY=1.15"
set "REPEAT_LAST_N=128"

set "SERVER_EXE="
for %%P in (
  "C:\Gillsystems\llama.cpp\bin\llama-server.exe"
  "%USERPROFILE%\src\llama.cpp\bin\llama-server.exe"
  "%USERPROFILE%\src\llama.cpp\build-vulkan-win\bin\Release\llama-server.exe"
  "%USERPROFILE%\src\llama.cpp\build-hip-win\bin\Release\llama-server.exe"
  "%USERPROFILE%\source\repos\llama.cpp\bin\llama-server.exe"
) do (
  if not defined SERVER_EXE if exist "%%~P" set "SERVER_EXE=%%~P"
)

if not defined SERVER_EXE (
  set "SERVER_EXE=C:\Gillsystems\llama.cpp\bin\llama-server.exe"
)

for %%I in ("%SERVER_EXE%") do set "SERVER_DIR=%%~dpI"
set "TENSILE_LIBPATH=%SERVER_DIR%rocblas\library"
set "LOG_DIR=%~dp0..\logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set "TIMESTAMP=%%I"
set "LOG_FILE=%LOG_DIR%\server_%COMPUTERNAME%_%TIMESTAMP%.log"

echo Binary:  %SERVER_EXE%
echo Model:   %MODEL_PATH%
echo Host:    %HOST%:%PORT%
echo Context: %CTX_SIZE%
echo Log:     %LOG_FILE%
echo.

if /I "%~1"=="--dry-run" (
  echo Dry run only. Command would launch the Laptop node configuration above.
  exit /b 0
)

if not exist "%SERVER_EXE%" (
  echo [Gillsystems] ERROR: llama-server.exe not found at "%SERVER_EXE%"
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
  echo [Gillsystems] ERROR: model not found at "%MODEL_PATH%"
    pause
    exit /b 1
)

echo [Gillsystems] Terminating any existing llama-server.exe instances...
taskkill /F /T /IM llama-server.exe >nul 2>&1
echo [Gillsystems] Waiting for Windows to release VRAM allocations...
timeout /t 3 /nobreak >nul

set "GS_SERVER_EXE=%SERVER_EXE%"
set "GS_MODEL_PATH=%MODEL_PATH%"
set "GS_HOST=%HOST%"
set "GS_PORT=%PORT%"
set "GS_CTX_SIZE=%CTX_SIZE%"
set "GS_N_PREDICT=%N_PREDICT%"
set "GS_GPU_LAYERS=%GPU_LAYERS%"
set "GS_PARALLEL_REQUESTS=%PARALLEL_REQUESTS%"
set "GS_FLASH_ATTN=%FLASH_ATTN%"
set "GS_BATCH_SIZE=%BATCH_SIZE%"
set "GS_UBATCH_SIZE=%UBATCH_SIZE%"
set "GS_CHAT_TEMPLATE=%CHAT_TEMPLATE%"
set "GS_TEMPERATURE=%TEMPERATURE%"
set "GS_TOP_K=%TOP_K%"
set "GS_TOP_P=%TOP_P%"
set "GS_REPEAT_PENALTY=%REPEAT_PENALTY%"
set "GS_REPEAT_LAST_N=%REPEAT_LAST_N%"
set "GS_TENSILE_LIBPATH=%TENSILE_LIBPATH%"
set "GS_USE_HIP_UMA=%USE_HIP_UMA%"
set "GS_LOG_FILE=%LOG_FILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "& { ^
      $ErrorActionPreference = 'Stop'; ^
      if (Test-Path $env:GS_TENSILE_LIBPATH) { $env:ROCBLAS_TENSILE_LIBPATH = $env:GS_TENSILE_LIBPATH; } ^
      if ($env:GS_USE_HIP_UMA -eq '1') { $env:LLAMA_HIP_UMA = '1'; } ^
      & $env:GS_SERVER_EXE ^
        '-m' $env:GS_MODEL_PATH ^
        '-c' $env:GS_CTX_SIZE ^
        '-n' $env:GS_N_PREDICT ^
        '-ngl' $env:GS_GPU_LAYERS ^
        '-fa' $env:GS_FLASH_ATTN ^
        '-np' $env:GS_PARALLEL_REQUESTS ^
        '-b' $env:GS_BATCH_SIZE ^
        '-ub' $env:GS_UBATCH_SIZE ^
        '--port' $env:GS_PORT ^
        '--host' $env:GS_HOST ^
        '--jinja' ^
        '--chat-template' $env:GS_CHAT_TEMPLATE ^
        '--context-shift' ^
        '--temperature' $env:GS_TEMPERATURE ^
        '--top-k' $env:GS_TOP_K ^
        '--top-p' $env:GS_TOP_P ^
        '--repeat-penalty' $env:GS_REPEAT_PENALTY ^
        '--repeat-last-n' $env:GS_REPEAT_LAST_N ^
        '--metrics' ^
        '--no-mmap' 2>&1 ^
      | Tee-Object -FilePath $env:GS_LOG_FILE -Append; ^
      exit $LASTEXITCODE ^
  }"

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if %EXIT_CODE% EQU 0 (
    echo [Gillsystems] Server exited cleanly.
) else if %EXIT_CODE% EQU 130 (
    echo [Gillsystems] Server cancelled by user.
) else (
    echo [Gillsystems] ERROR: Server exited with code %EXIT_CODE%
    echo [Gillsystems] Review log: %LOG_FILE%
)

pause
exit /b %EXIT_CODE%