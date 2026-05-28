@echo off
echo Starting Gillsystems-Main LLM Server... LOCKED IN RADEON 7900XTX!
cd /d "C:\Gillsystems\llama.cpp\bin\"

llama-server.exe ^
  -m "C:\Models\gemma-4-31B.Q4_K_M.gguf" ^
  -c 65536 ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  -b 2048 ^
  -ub 512 ^
  --port 8010 ^
  --host 10.0.0.164 ^
  --temperature 1.0 ^
  --top-k 64 ^
  --top-p 0.95 ^
  -r "<|im_end|>,<|im_start|>" ^
  --metrics ^
  --no-mmap

pause