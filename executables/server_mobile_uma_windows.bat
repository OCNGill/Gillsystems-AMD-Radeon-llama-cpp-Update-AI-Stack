@echo off
setlocal EnableExtensions

echo Starting mobile-node LLM Server... Vulkan Backend.

set "LLAMA_EXE=C:\llama.cpp\bin\llama-server.exe"
set "MODEL=(C:\Users\<user>) Laptop\Desktop\Models\gemma-4-E4B.Q6_K.gguf"
set "CTX_SIZE=32768"

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
  -c %CTX_SIZE% ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  -b 2048 ^
  -ub 512 ^
  --port 8012 ^
  --host 192.0.2.93 ^
  --context-shift ^
  --temperature 1.0 ^
  --top-k 64 ^
  --top-p 0.95 ^
  -r "<|im_end|>,<|im_start|>" ^
  --metrics ^
  --no-mmap

pause