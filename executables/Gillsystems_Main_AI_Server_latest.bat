@echo off
echo Starting Gillsystems-Main LLM Server..LOCKED IN RADEON 7900XTX!
cd /d "C:\Gillsystems\llama.cpp\bin\"

llama-server.exe ^
  -m "C:\Models\gemma-4-31B.Q4_K_M.gguf" ^
  -c 49152 ^
  -ngl 99 ^
  -fa on ^
  -np 1 ^
  --port 8010 ^
  --host 10.0.0.164 ^
  --chat-template chatml ^
  --context-shift ^
  --temperature 0.20 ^
  --top-k 20 ^
  --min-p 0.05 ^
  --metrics ^
  --no-mmap

pause