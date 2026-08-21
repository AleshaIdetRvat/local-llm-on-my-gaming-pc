@echo off
rem args: %1 = n-cpu-moe, %2 = spec-draft-n-max
cd /d C:\llm\llama.cpp
llama-server.exe -m C:\llm\models\qwen36-35b\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf --host 0.0.0.0 --port 8080 -ngl 999 --n-cpu-moe %1 -np 1 -c 102400 -fa on --cache-type-k q8_0 --cache-type-v q8_0 -t 6 -b 2048 -ub 2048 --ctx-checkpoints 8 --checkpoint-min-step 1024 --spec-type draft-mtp --spec-draft-n-max %2 --jinja > C:\Users\Public\llama-mtp.log 2>&1
