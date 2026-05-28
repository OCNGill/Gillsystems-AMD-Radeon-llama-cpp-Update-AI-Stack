@echo off
setlocal EnableExtensions

echo Starting Gillsystems-Laptop LLM Server... Vulkan Backend.

set "LLAMA_EXE=C:\llama.cpp\bin\llama-server.exe"
set "MODEL=C:\Users\Gillsystems Laptop\Desktop\Models\gemma-4-E4B.Q6_K.gguf"
set "CTX_SIZE=32768"

:: Google Authoritative Model Card Sampling Stack
set "TEMPERATURE=0.20"
set "TOP_K=20"
set "MIN_P=0.05"

if not exist "%LLAMA_EXE%" (
    echo [Gillsystems] ERROR: llama-server.exe not found at "%LLAMA_EXE%"
    pause
    exit /b 1
)

if not exist "%MODEL%" (
    echo [Gillsystems] ERROR: model not found at "%MODEL%"
    pause
    exit /b 1
)

echo [Gillsystems] Terminating any existing llama-server.exe instances...
taskkill /F /T /IM llama-server.exe >nul 2>&1
echo [Gillsystems] Waiting for Windows to release VRAM allocations...
timeout /t 3 /nobreak >nul

"%LLAMA_EXE%" ^
  -m "%MODEL%" ^
  -c %CTX_SIZE% ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  -b 2048 ^
  -ub 512 ^
  --port 8012 ^
  --host 10.0.0.93 ^
  --context-shift ^
  --temperature %TEMPERATURE% ^
  --top-k %TOP_K% ^
  --min-p %MIN_P% ^
  --repeat-penalty 1.15 ^
  --repeat-last-n 128 ^
  -r "<|im_end|>,<|im_start|>" ^
  --metrics ^
  --no-mmap

pause