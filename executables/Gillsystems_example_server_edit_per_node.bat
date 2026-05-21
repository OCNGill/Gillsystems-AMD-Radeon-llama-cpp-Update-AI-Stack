@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

:: ============================================================
:: Gillsystems Example Server Launcher (Windows)
:: Edit the values below for each node before production use.
::
:: Note: Gemma 4 MTP flags are intentionally omitted for now.
:: Current upstream GGUF conversion does not emit Gemma MTP layers,
:: so forcing draft-mtp will fail model load.
:: ============================================================

set "LLAMA_BIN_DIR=C:\Gillsystems\llama.cpp\bin"
set "MODEL_PATH=C:\Models\gemma-4-31B.Q4_K_M.gguf"
set "HOST=0.0.0.0"
set "PORT=8010"
set "CTX_SIZE=102400"
set "GPU_LAYERS=99"
set "PARALLEL_REQUESTS=1"
set "FLASH_ATTN=on"
set "CACHE_TYPE_K=q4_0"
set "CACHE_TYPE_V=q4_0"

set "SERVER_EXE=%LLAMA_BIN_DIR%\llama-server.exe"
set "TENSILE_LIBPATH=%LLAMA_BIN_DIR%\rocblas\library"
set "LOG_DIR=%~dp0logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set "TIMESTAMP=%%I"
set "NODE_NAME=%COMPUTERNAME%"
set "LOG_FILE=%LOG_DIR%\server_%NODE_NAME%_%TIMESTAMP%.log"

echo Starting Gillsystems example server...
echo Model: %MODEL_PATH%
echo Log:   %LOG_FILE%
echo.

if /I "%~1"=="--dry-run" (
    echo Dry run only. Command would launch llama-server.exe with the configuration above.
    exit /b 0
)

if not exist "%SERVER_EXE%" (
    echo  [Gillsystems] ERROR: llama-server.exe not found at "%SERVER_EXE%"
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
    echo  [Gillsystems] ERROR: Model not found at "%MODEL_PATH%"
    pause
    exit /b 1
)

set "GS_SERVER_EXE=%SERVER_EXE%"
set "GS_MODEL_PATH=%MODEL_PATH%"
set "GS_HOST=%HOST%"
set "GS_PORT=%PORT%"
set "GS_CTX_SIZE=%CTX_SIZE%"
set "GS_GPU_LAYERS=%GPU_LAYERS%"
set "GS_PARALLEL_REQUESTS=%PARALLEL_REQUESTS%"
set "GS_FLASH_ATTN=%FLASH_ATTN%"
set "GS_CACHE_TYPE_K=%CACHE_TYPE_K%"
set "GS_CACHE_TYPE_V=%CACHE_TYPE_V%"
set "GS_TENSILE_LIBPATH=%TENSILE_LIBPATH%"
set "GS_LOG_FILE=%LOG_FILE%"

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
        '--cache-type-k' $env:GS_CACHE_TYPE_K ^
        '--cache-type-v' $env:GS_CACHE_TYPE_V ^
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