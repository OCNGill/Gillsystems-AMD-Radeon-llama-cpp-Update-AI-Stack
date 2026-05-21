@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

:: ============================================================
:: Gillsystems Laptop iGPU Server Launcher (Windows / Tier 2)
:: Dedicated second-set example launcher for the Laptop / Vega 6 node.
::
:: Prefers the clean source-root bin path if present, but falls back to
:: the current Visual Studio build output tree and then the canonical
:: install root so the example remains usable during transition.
:: ============================================================

set "MODEL_PATH=C:\Users\Gillsystems Laptop\Desktop\Models\gemma-4-E4B.Q6_K.gguf"
set "HOST=10.0.0.93"
set "PORT=8012"
set "CTX_SIZE=49152"
set "GPU_LAYERS=99"
set "PARALLEL_REQUESTS=1"
set "FLASH_ATTN=on"
set "TEMPERATURE=0.20"
set "TOP_K=20"
set "MIN_P=0.05"
set "LOG_DIR=%~dp0..\logs"

set "SERVER_EXE="
for %%P in (
  "C:\llama.cpp\bin\llama-server.exe"
  "C:\llama.cpp\build-hip-win\bin\Release\llama-server.exe"
  "C:\Gillsystems\llama.cpp\bin\llama-server.exe"
) do (
  if not defined SERVER_EXE if exist %%~P set "SERVER_EXE=%%~P"
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set "TIMESTAMP=%%I"
set "NODE_NAME=%COMPUTERNAME%"
set "LOG_FILE=%LOG_DIR%\server_%NODE_NAME%_%TIMESTAMP%.log"

echo Starting Gillsystems Laptop iGPU example server...
echo Model: %MODEL_PATH%
echo Log:   %LOG_FILE%
echo.

if /I "%~1"=="--dry-run" (
    echo Dry run only. Command would launch the Laptop / Tier 2 server configuration above.
    exit /b 0
)

if not defined SERVER_EXE (
    echo  [Gillsystems] ERROR: llama-server.exe was not found in any expected Laptop path.
    echo  [Gillsystems] Checked: C:\llama.cpp\bin, C:\llama.cpp\build-hip-win\bin\Release, C:\Gillsystems\llama.cpp\bin
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
    echo  [Gillsystems] ERROR: Model not found at "%MODEL_PATH%"
    pause
    exit /b 1
)

for %%I in ("%SERVER_EXE%") do set "LLAMA_BIN_DIR=%%~dpI"
if "!LLAMA_BIN_DIR:~-1!"=="\" set "LLAMA_BIN_DIR=!LLAMA_BIN_DIR:~0,-1!"
set "TENSILE_LIBPATH=!LLAMA_BIN_DIR!\rocblas\library"

set "GS_SERVER_EXE=%SERVER_EXE%"
set "GS_MODEL_PATH=%MODEL_PATH%"
set "GS_HOST=%HOST%"
set "GS_PORT=%PORT%"
set "GS_CTX_SIZE=%CTX_SIZE%"
set "GS_GPU_LAYERS=%GPU_LAYERS%"
set "GS_PARALLEL_REQUESTS=%PARALLEL_REQUESTS%"
set "GS_FLASH_ATTN=%FLASH_ATTN%"
set "GS_TEMPERATURE=%TEMPERATURE%"
set "GS_TOP_K=%TOP_K%"
set "GS_MIN_P=%MIN_P%"
set "GS_TENSILE_LIBPATH=%TENSILE_LIBPATH%"
set "GS_LOG_FILE=%LOG_FILE%"

echo Executable: %SERVER_EXE%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "& { ^
      $ErrorActionPreference = 'Stop'; ^
      if (Test-Path $env:GS_TENSILE_LIBPATH) { $env:ROCBLAS_TENSILE_LIBPATH = $env:GS_TENSILE_LIBPATH; } ^
      & $env:GS_SERVER_EXE ^
        '-m' $env:GS_MODEL_PATH ^
        '-c' $env:GS_CTX_SIZE ^
        '-ngl' $env:GS_GPU_LAYERS ^
        '-fa' $env:GS_FLASH_ATTN ^
        '-np' $env:GS_PARALLEL_REQUESTS ^
        '--port' $env:GS_PORT ^
        '--host' $env:GS_HOST ^
        '--jinja' ^
        '--context-shift' ^
        '--temperature' $env:GS_TEMPERATURE ^
        '--top-k' $env:GS_TOP_K ^
        '--min-p' $env:GS_MIN_P ^
        '--metrics' ^
        '--no-mmap' 2>&1 ^
      | Tee-Object -FilePath $env:GS_LOG_FILE -Append; ^
      exit $LASTEXITCODE ^
  }"

set "EXIT_CODE=%ERRORLEVEL%"
echo.
if %EXIT_CODE% EQU 0 (
    echo  [Gillsystems] Server exited cleanly.
) else if %EXIT_CODE% EQU 130 (
    echo  [Gillsystems] Server cancelled by user.
) else (
    echo  [Gillsystems] ERROR: Server exited with code %EXIT_CODE%
    echo  [Gillsystems] Review log: %LOG_FILE%
)

pause
exit /b %EXIT_CODE%