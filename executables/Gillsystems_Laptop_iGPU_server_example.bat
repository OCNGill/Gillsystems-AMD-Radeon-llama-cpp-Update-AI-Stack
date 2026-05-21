@echo off
setlocal EnableExtensions

echo Starting Gillsystems-Laptop LLM Server... Vulkan Backend.

set "LLAMA_EXE=C:\llama.cpp\bin\llama-server.exe"
set "MODEL=C:\Users\Gillsystems Laptop\Desktop\Models\gemma-4-E4B.Q6_K.gguf"

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

"%LLAMA_EXE%" ^
  -m "%MODEL%" ^
  -c 32768 ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  --port 8012 ^
  --host 10.0.0.93 ^
  --chat-template gemma ^
  --context-shift ^
  --temperature 0.20 ^
  --top-k 20 ^
  --min-p 0.05 ^
  --metrics ^
  --no-mmap

pause