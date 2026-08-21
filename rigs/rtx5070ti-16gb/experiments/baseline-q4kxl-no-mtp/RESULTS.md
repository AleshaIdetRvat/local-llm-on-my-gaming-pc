# Baseline — Qwen3.6-35B-A3B UD-Q4_K_XL, БЕЗ MTP (замороженный рабочий конфиг)

> Снимок сделан **2026-07-01**. Это «золотой» референс перед экспериментом с MTP-версией.
> Всё измерено и подтверждено живьём по SSH; сервер на момент снимка был поднят и отвечал.
> Файлы рядом: `run.bat` (байт-точная копия `C:\llm\run.bat` с ПК) и `run.ps1` (зеркало для репо).

## Железо и софт (сверено по факту)
| | |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti, 16303 MiB (16 ГБ), sm_120 Blackwell |
| Драйвер | 610.62 |
| CPU | Ryzen 5 7400F (6c/12t) |
| RAM | 32 ГБ (free ~5 ГБ при работающем сервере) |
| ОС | Windows 11, нативно |
| Движок | llama.cpp `llama-server`, **build b9851 (0eca4d490)**, пребилт **cuda-13.3**, Clang 20.1.8 |
| Хост | `$RIG_SSH_USER@$RIG_HOST`, API на `$RIG_API` |

## Модель
| | |
|---|---|
| Репо | `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` |
| Файл | `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` |
| Размер | **22 853 663 008 байт** (22.85 ГБ), байт-точно сверено |
| Путь на ПК | `C:\llm\models\qwen36-35b\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` |
| MTP | **выключен** (без `--spec-type draft-mtp`), хотя голова в файле есть — это baseline для сравнения |
| Архитектура | MoE 256+1 эксперт, top-8 (→9 модулей/токен, A3B); 40 слоёв = 30 Gated DeltaNet + 10 full-attention |

## Итоговый конфиг запуска
```
llama-server.exe ^
  -m C:\llm\models\qwen36-35b\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf ^
  --host 0.0.0.0 --port 8080 ^
  -ngl 999 --n-cpu-moe 20 -np 1 ^
  -c 102400 -fa on ^
  --cache-type-k q8_0 --cache-type-v q8_0 ^
  -t 6 -b 2048 -ub 2048 ^
  --ctx-checkpoints 8 --checkpoint-min-step 1024 ^
  --jinja
```

## Замеры (финальный конфиг, контекст 102400, KV q8_0, flash-attn)
Тёплый GPU, промпт ~6.3К токенов, через `/completion`:

| Метрика | Значение |
|---|---|
| **decode (tg)** | **~66–70 tok/s** |
| **prefill (pp)** | **~2830 tok/s** (при `-ub 2048`) |
| **VRAM** | **~15.5 ГБ / 16.3 ГБ** (пик ~15510 MiB; снято 15377 MiB на живом сервере) |
| Крашей / OOM | нет; MMQ работает |

### Свип `-ub` (тот же промпт, тёплый прогон)
| `-ub` | prefill | VRAM |
|---|---|---|
| 512  | ~1415 pp | 14998 MiB |
| 1024 | ~2110 pp (+48% к 512) | 15124 MiB |
| **2048** | **~2827 pp** (+34% к 1024, ×2 к 512) | **15510 MiB** (запас ~790 MiB) ← выбран |

VRAM растёт линейно (~+250 MiB на удвоение `-ub`), пик резервируется при загрузке графа, с длиной промпта не растёт (KV аллоцируется целиком при старте). Prefill тут bandwidth-bound (эксперты 20 слоёв на CPU/RAM), не GPU-bound → больший `-ub` амортизирует поток весов экспертов из RAM.

### Свип `--n-cpu-moe`
| N | VRAM | prefill | decode |
|---|---|---|---|
| 30 | 10.5 ГБ | 521 pp | 53 tg |
| 22 | 14.1 ГБ | 840 pp | 57 tg |
| **20** | **15.1 ГБ** | — | **61 tg** ← выбран |

Ниже 18 опасно (≈15.9 ГБ, мало запаса под десктоп). KV на 102400 аллоцируется целиком при загрузке → VRAM фиксирована, с контекстом не растёт.

## Переиспользование префикса (context checkpoints)
- `--cache-reuse` (KV-shift) на этой recurrent-модели **не работает** — убран (был no-op): `cache_reuse is not supported by this context`.
- Рабочий механизм — **context checkpoints** (снимок рекуррентного состояния слота), жив на b9851. Дефолтный `--checkpoint-min-step 8192` душит его на ходах < 8К → поставили `--ctx-checkpoints 8 --checkpoint-min-step 1024`.
- Результат: повтор той же растущей истории реюзается почти полностью — **reprocess 4 токена вместо ~2048** (прод: B=3607 → B-повтор=4).
- Ограничение: смена префикса (Plan↔Build system-промпт / другая сессия) требует reprocess от ближайшего checkpoint (worst-case ~1–2К токенов ≈ <1с) — свойство рекуррентной архитектуры, конфигом не лечится.
- Checkpoint'ы живут в **RAM** (~150 MiB × 8 ≈ 1.2 ГБ), **VRAM не трогают**.

## Автозапуск
Задача планировщика `llama-server`: принципал `llm` (S4U, RunLevel Highest), триггер At Startup, действие `cmd /c C:\llm\run.bat`, RestartCount 3. Session 0 на этом ПК имеет доступ к GPU. Лог: `C:\Users\Public\llama-server.log`.
- Стоп/старт (десктоп `<desktop-user>`): ярлыки `C:\llm\stop-llm.bat` / `C:\llm\start-llm.bat`.
- По SSH: `schtasks /Run|/End /TN llama-server`.

## Как воспроизвести этот baseline
1. На ПК `C:\llm\run.bat` = `run.bat` из этой папки (байт-точно).
2. Билд llama.cpp = b9851 cuda-13.3.
3. Запуск: `schtasks /Run /TN llama-server` (или двойной клик «LLM — включить»).
