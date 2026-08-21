@echo off
REM llama-swap - proxy on 0.0.0.0:8080/v1, hot-swaps models per request field.
REM Config: C:\llm\llama-swap\config.yaml. --watch-config auto-reloads config edits.
cd /d C:\llm\llama-swap
llama-swap.exe --config C:\llm\llama-swap\config.yaml --listen 0.0.0.0:8080 --watch-config > C:\Users\Public\llama-swap.log 2>&1
