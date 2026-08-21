# Финальный конфиг llama-server — Qwen3.6-35B-A3B UD-Q4_K_XL на RTX 5070 Ti
# Движок: llama.cpp b9851, пребилт cuda-13.3 (на ПК лежит в C:\llm\llama.cpp).
# Замерено (контекст 102400, KV q8_0, flash-attn, тёплый GPU, промпт ~6.3К через /completion):
#   prefill ~2830 tok/s (ub 2048) · decode ~66-70 tok/s · VRAM ~15.5 ГБ / 16.3 ГБ (пик).
#
# MTP протестирован (2026-07-01) и ОТКАЧЕН обратно на baseline (2026-07-02) по решению.
#   Замеры: --spec-type draft-mtp --spec-draft-n-max 1 давал decode ~79-81 tok/s (+11% к 73.6),
#   acceptance ~85-89%, prefill без изменений, ценой ~300 MiB VRAM (запас ужимался 790→490 MiB).
#   n-max 2 = -4%, дефолтный n-max 3 = -34%. Полный разбор — mtp-experiment-2026-07-01/RESULTS.md.
#   Если захочется вернуть: добавить `--spec-type draft-mtp --spec-draft-n-max 1` (только n-max 1).
#
# Тюнинг -ub (тот же промпт, тёплый прогон, 2026-07-01):
#   512  → ~1415 pp / 14998 MiB
#   1024 → ~2110 pp / 15124 MiB   (+48% к 512)
#   2048 → ~2827 pp / 15510 MiB   ← выбран: +34% к 1024, ×2 к 512; пик VRAM, запас ~790 MiB
# Масштабирование VRAM линейное (~+250 MiB на удвоение -ub), OOM нет, n-cpu-moe остался 20.
# Bottleneck prefill тут bandwidth-bound (эксперты первых 20 слоёв на CPU/RAM), не GPU —
# больший -ub амортизирует поток весов экспертов из RAM по большему числу токенов за проход.
#
# Переиспользование префикса (агентский цикл: стабильный system-промпт + растущая история). Замерено 2026-07-01:
#   • --cache-reuse (KV-shift) на этой модели НЕ работает и УБРАН (был no-op): рекуррентные Gated
#     DeltaNet-слои нельзя «сдвинуть», в логе было "cache_reuse is not supported by this context".
#   • Рабочий механизм — context checkpoints (снимок рекуррентного состояния), он ЖИВ на b9851. Но
#     дефолтный --checkpoint-min-step 8192 душит его на промптах короче 8К → внутри них checkpoint не
#     создаётся. Поставили min-step 1024 + ctx-checkpoints 8: повтор той же растущей истории реюзается
#     почти полностью — reprocess 4 токена вместо ~2048 (проверено на проде: B=3607 → B-повтор=4).
#   • Смена префикса (напр. Plan↔Build system-промпт / другая сессия) всё равно требует reprocess от
#     ближайшего checkpoint (worst-case ~1-2К токенов ≈ <1с) — ограничение рекуррентной архитектуры,
#     конфигом не лечится (см. llama.cpp #22354/#22384/#24055; ik_llama.cpp #1762 — там тоже сломано).
#   Checkpoint'ы живут в RAM (~150 MiB × 8 ≈ 1.2 ГБ), VRAM НЕ трогают (осталось 15478 MiB). RAM free ~5 ГБ.
#   Значения min-step/ctx-checkpoints стоит перетюнить под реальные размеры ходов агента в Фазе 4/7.
#
# На ПК этому файлу соответствует C:\llm\run.bat (байт-точная копия рядом: run-qwen.bat).
# С 2026-07-08 прод идёт через llama-swap (см. config.yaml) — run.bat остался как откат
# на прямой llama-server; флаги модели в config.yaml те же.
# Vision добавлен 2026-07-06: --mmproj (энкодер картинок на CPU, чтобы не есть VRAM).
# Если играешь и нужна VRAM — подними --n-cpu-moe (28-30 освобождает ~2-5 ГБ ценой скорости).

& 'C:\llm\llama.cpp\llama-server.exe' `
  -m 'C:\llm\models\qwen36-35b\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf' `
  --host 0.0.0.0 --port 8080 `
  -ngl 999 --n-cpu-moe 20 -np 1 `
  -c 102400 -fa on `
  --cache-type-k q8_0 --cache-type-v q8_0 `
  -t 6 -b 2048 -ub 2048 `
  --ctx-checkpoints 8 --checkpoint-min-step 1024 `
  --mmproj 'C:\llm\models\qwen36-35b\mmproj-F16.gguf' --no-mmproj-offload `
  --jinja
