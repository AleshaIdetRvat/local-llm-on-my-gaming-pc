# Хронология чекпоинтов

Архив статус-чекпоинтов из бывшего `PLAN.md` (разбит по файлам 2026-07-23, текст сохранён verbatim).
Каждый файл — самодостаточный снимок «что сделали и почему» на свою дату. Историю не переписываем — только дописываем новые файлы.

> ⚠️ Пути к файлам репо внутри чекпоинтов могут отражать старую структуру:
> `llama-swap/` → теперь `bench/` + `pc-mirrors/`; `baseline-q4kxl-no-mtp/` и
> `mtp-experiment-2026-07-01/` → теперь в `experiments/`; сам `PLAN.md` → `docs/`.
> Пути на ПК (`C:\llm\...`) актуальны.

| Дата | Файл | Суть |
|---|---|---|
| 2026-07-01 | [baseline-qwen](2026-07-01-baseline-qwen.md) | Первый рабочий сервер: Qwen3.6-35B-A3B, тюнинг `--n-cpu-moe`/`-ub`, context checkpoints, автозапуск |
| 2026-07-02 | [glm-reap-23b](2026-07-02a-glm-reap-23b.md) | GLM-4.7-Flash-REAP-23B на 128K, находка про спилловер VRAM (суперседед) |
| 2026-07-02 | [glm-full](2026-07-02b-glm-full.md) | Полная GLM-4.7-Flash, тюнинг ub → 2617 pp (суперседед откатом 04.07) |
| 2026-07-04 | [revert-to-qwen](2026-07-04-revert-to-qwen.md) | Прод возвращён на Qwen |
| 2026-07-06 | [qwen-vision](2026-07-06-qwen-vision.md) | Включено зрение на Qwen (mmproj на CPU) |
| 2026-07-08 | [llama-swap](2026-07-08a-llama-swap.md) | Поставлен llama-swap: горячая смена моделей, TTL, `--reasoning-preserve`, оверхеда нет |
| 2026-07-08 | [bench-ctx + gemma-12b](2026-07-08b-bench-ctx-gemma-12b.md) | Новый метод бенча (свип по глубине контекста), добавлена Gemma 4 12B QAT |
| 2026-07-08 | [gemma-26b](2026-07-08c-gemma-26b.md) | Gemma 4 26B-A4B QAT — лучшая ≤32K, thinking через env, `--watch-config` |
| 2026-07-09 | [autostart-fix](2026-07-09-autostart-fix.md) | Fast Startup ломал BootTrigger → добавлен LogonTrigger |
| 2026-07-10 | [parallel-np2-incident](2026-07-10-parallel-np2-incident.md) | `-np 2` на gemma-26b (+47% суммарно) + инцидент repetition-loop (DRY — кандидат, не внедрён) |
| 2026-07-17 | [ternary-bonsai-27b](2026-07-17-ternary-bonsai-27b.md) | Ternary/BitNet 27B (7.17 ГБ) через форк llama.cpp PrismML |
| 2026-07-29 | [transcribe-pipeline](2026-07-29-transcribe-pipeline.md) | Пайплайн транскрибации созвонов: WhisperX + pyannote на ПК, выжимка через прод-Qwen. Прод не менялся |
