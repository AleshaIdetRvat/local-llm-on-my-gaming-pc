# Модели стенда rtx5070ti-16gb

> Карточки моделей, подобранных под RTX 5070 Ti 16 ГБ. Как подбирать под свою карту —
> [docs/choosing-models.md](../../docs/choosing-models.md).
>
> Все конфиг-блоки — в [`pc-mirrors/config.yaml`](pc-mirrors/config.yaml) (зеркало ПК).
> Замеры — в [benchmarks.md](benchmarks.md), методика — [docs/benchmarks.md](../../docs/benchmarks.md). Скорости ниже: pp = prefill, tg = decode, tok/s.

## Сводка

| `model` | Что это | GGUF (квант / размер) | Контекст | pp / tg @~8K | VRAM |
|---|---|---|---|---|---|
| `qwen3.6-35b-a3b` (алиас `default`) | MoE 35B, ~3B актив. | UD-Q4_K_XL · 22.85 ГБ | 100K | 3126 / 70.4 | 14852 |
| `gemma-4-26b-a4b-qat` | MoE 26B, ~4B актив., QAT | UD-Q4_K_XL · 13.3 ГиБ | 32K (`-np 2` → 2×16K) | 6694 / 164.6 | 15129 |
| `gemma-4-26b-a4b-qat-nothink` | она же, `enable_thinking=false` | те же веса | 32K (`-np 2` → 2×16K) | те же | те же |
| `gemma-4-12b-qat` | dense 12B, QAT | UD-Q4_K_XL · 6.72 ГБ | 64K | 4105 / 85.7 | 8990 |
| `glm-4.7-flash` | MoE, 64 эксперта (полная) | UD-Q4_K_XL · 17.52 ГБ | 128K | 2617 / 63.5 (@~6K) | 15839 пик |
| `glm-4.7-flash-reap-23b` | REAP-прун GLM (Cerebras) | UD-Q4_K_XL · 14.24 ГБ | 128K | 2350 / 87.5 (@~6K) | 15822 |
| `ternary-bonsai-27b` | ternary/BitNet dense 27B | Q2_0_g128 · 7.17 ГБ | 100K (нативно 262K) | проба: tg ~64 | 8845 (@32K) |
| `qwen3.8-27b` | dense 27B, гибрид. attention | UD-Q3_K_XL · 13.15 ГБ | **128K** (нативно 262K) | 1744 / 49.4 | 15467 пик |
| `qwen3.8-27b-q8kv` | она же, KV в `q8_0` | те же веса | 64K | 1553 / 44.0 (@32K) | 15081 |

**Какую брать:**
- **≤32K, максимум скорости** → `gemma-4-26b-a4b-qat` (в ~2× быстрее всех, MoE целиком в VRAM; держит 2 параллельных запроса).
- **64K** → `gemma-4-12b-qat`.
- **100K, vision, агентный цикл** → `qwen3.6-35b-a3b` (прод, `default`).
- **128K** → `glm-4.7-flash-reap-23b` (скорость) или `glm-4.7-flash` (полное качество; REAP заявлен near-lossless, так что выигрыш full может быть мал).
- **128K + самая свежая модель** → `qwen3.8-27b` (медленнее GLM по prefill, но это dense-27B с гибридной attention и нативными 262K).
- **Эксперимент** → `ternary-bonsai-27b`.

---

## qwen3.6-35b-a3b — прод (алиас `default`)

- **Репо:** `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` → `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` (22 853 663 008 Б).
- **Архитектура:** MoE 256+1 экспертов, top-8 (A3B); 40 слоёв = 30 Gated DeltaNet (linear, рекуррентное состояние фикс-размера) + 10 full-attention → KV на 100K всего ~1 ГБ в q8_0.
- **Конфиг:** `--n-cpu-moe 20` (эксперты 20 слоёв в RAM — модель не влезает в 16 ГБ), `-c 102400 -ub 2048`, `--ctx-checkpoints 8 --checkpoint-min-step 1024`, `--reasoning-preserve`, сэмплинг Qwen `0.6 / 0.95 / 20`.
- **Vision включён:** `--mmproj mmproj-F16.gguf --no-mmproj-offload` (энкодер на CPU; тёплое фото ~2.3 с). Картинки — OpenAI-формат `image_url` / base64 data URI.
- **Префикс-реюз:** `--cache-reuse` НЕ работает (рекуррентные слои) — работают context checkpoints: повтор растущей истории реюзается почти полностью (reprocess 4 ток. вместо ~2048); смена system-промпта = reprocess от ближайшего checkpoint (~1–2K ток.). Checkpoint'ы в RAM (~1.2 ГБ), VRAM не трогают.
- **Thinking:** включён по умолчанию; выключить пер-запрос: `"chat_template_kwargs":{"enable_thinking":false}`.
- **MTP:** голова в GGUF есть, но прод без MTP (только `n-max 1` давал +11%, см. [experiments/mtp-experiment-2026-07-01](experiments/mtp-experiment-2026-07-01/RESULTS.md)).

## gemma-4-26b-a4b-qat — быстрейшая ≤32K

- **Репо:** `unsloth/gemma-4-26B-A4B-it-qat-GGUF` (QAT = 4-бит чекпоинт с качеством near-BF16). 30 слоёв, 128 экспертов top-8, гибрид 24 sliding-window(1024) + 6 full-attention → KV дёшев.
- **Конфиг:** целиком на GPU (без `--n-cpu-moe`), `-c 32768 -ub 512` (больший ub не влезает), **`-np 2`** — 2 параллельных слота жёстко по 16K каждый; сэмплинг Google `1.0 / 0.95 / 64`.
- **Параллелизм:** 2 запроса идут одновременно: per-req tg ~117–96, суммарно ~192–235 (+47% пропускной), спилла нет. Потолок одного запроса = 16K; вернуть один слот на полные 32K = убрать `-np 2`.
- **Thinking:** шаблон Gemma в `/chat`-пути глушит его по умолчанию → **форсим ON через env** `LLAMA_ARG_CHAT_TEMPLATE_KWARGS={"enable_thinking":true}` (через env, т.к. llama-swap не снимает кавычки у cmd-line JSON). `--reasoning-preserve` не нужен — эквивалент встроен в шаблон (reasoning переподаётся за tool_call'ами текущего хода; клиент должен возвращать `reasoning_content`).
- **Близнец без reasoning:** `gemma-4-26b-a4b-qat-nothink` — та же модель/контекст/сэмплинг, отличие ровно в `enable_thinking=false`. Для задач, где reasoning только жрёт токены и латентность (проверено 2026-08-07: `reasoning_content` пустой, ответ сразу). Отдельная запись, а не пер-запросный `chat_template_kwargs`, — чтобы клиенты вроде Hermes могли выбирать режим одним полем `model`; переключение между близнецами = перезагрузка модели llama-swap'ом (~10–30 с).
- **⚠️ Известная патология:** repetition-loop (инцидент 2026-07-10, зацикливание `//s://s:` до упора в контекст). Фиксы не внедрены; кандидаты: выключать thinking на простых стадиях, DRY-сэмплер (`--dry-multiplier 0.8`) после A/B, клиентский `max_tokens`+retry на `finish=length`. Детали: [чекпоинт](history/2026-07-10-parallel-np2-incident.md).
- На диске ПК лежат неиспользуемые: MTP-драфтер (спекулятивный декод — не пробовали), mmproj не качали.

## gemma-4-12b-qat

- **Репо:** `unsloth/gemma-4-12B-it-qat-GGUF`. Dense 12B → целиком на GPU.
- **Конфиг:** `-c 65536 -ub 2048`, сэмплинг Google `1.0 / 0.95 / 64`; thinking форсится через env (как у 26B).
- VRAM всего 8990 → большой запас; на 128K было впритык (14852), откатились на 64K.
- Vision-файл (`mmproj-F16.gguf`) на диске есть, из конфига убран (мёртвый).

## glm-4.7-flash (полная) и glm-4.7-flash-reap-23b

- **Репо:** `unsloth/GLM-4.7-Flash-GGUF` и `unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF` (REAP-прун Cerebras: 64→прунёные эксперты, заявлен near-lossless, HumanEval 94.5→95.1).
- **Архитектура:** `glm4_moe_lite` / MLA (deepseek2-семейство), 47 слоёв, 64 routed + 1 shared, 4 активных/токен, нативный контекст ~202K.
- **Конфиг full:** `--n-cpu-moe 19 -c 131072 -ub 2048`, сэмплинг Z.ai tool-calling `0.7 / 1.0 / min-p 0.01 / rp 1.0`. **REAP:** `--n-cpu-moe 8 -c 131072 -ub 512` (⚠️ ub 1024 на 128K = спилловер, pp падает до 98).
- Оба с `--reasoning-preserve` (шаблон поддерживает, z.ai-механика). Thinking по умолчанию включён.
- REAP доминирует по скорости; полная — только ради качества всех 64 экспертов.

## ternary-bonsai-27b — эксперимент (BitNet)

- **Репо:** `prism-ml/Ternary-Bonsai-27B-gguf` → **`Ternary-Bonsai-27B-Q2_0.gguf`** = формат **g128** (7 165 121 600 Б). Веса {−1,0,+1} ≈ 1.71 бит/вес → dense 27B в 7.17 ГБ. База Qwen3.6-27B (гибрид ~75% linear + ~25% full attention), нативный контекст 262K.
- **⚠️ Работает ТОЛЬКО на форке `PrismML-Eng/llama.cpp`** (`C:\llm\llama.cpp-prism\`, релиз `prism-b9591`, cuda-12.4): кванты в кастомном ggml-типе 42, сток b9851 файл не читает. Файл `Q2_g64` несовместим и с форк-бинарём (другая упаковка масштабов) — удалён.
- **Blackwell через PTX-JIT:** пребилт без sm_120 → одноразовый прогрев ~24 с при холодной загрузке, дальше нормально.
- **Конфиг:** свой exe (не макрос `${server}`), `-c 102400`, сэмплинг Qwen `0.6 / 0.95 / 20`. Dense → целиком на GPU, без оффлоада.
- **Очень «думающая»:** на простой вопрос уходит в `<think>` на сотни токенов — для коротких ответов слать `"chat_template_kwargs":{"enable_thinking":false}` или большой `max_tokens`.
- Не сделано: честный бенч, драфтер `dspark` (заявлено ~1.34×), vision, оценка качества.

## qwen3.8-27b (+ близнец `qwen3.8-27b-q8kv`)

- **Репо:** `unsloth/Qwen3.8-27B-GGUF` → **`Qwen3.8-27B-UD-Q3_K_XL.gguf`** (13 146 393 504 Б).
- **Архитектура `qwen35`** (та же семья, что Qwen3.6): dense 27B, но attention гибридная —
  из 64 слоёв **16 full-attention** (`full_attention_interval = 4`), остальные 48 — линейные
  Gated DeltaNet, у которых KV не растёт. Нативный контекст 262K, есть vision (mmproj отдельно).
- **KV дёшев:** `16 × 4 головы × 256 head_dim × 2` = 32768 элементов на токен →
  64 КБ/ток в f16, 34 КБ в `q8_0`, **18 КБ в `q4_0`**. Поэтому 128K и влезают.
- **⚠️ Нужен свежий llama.cpp** — стоит **b10630** отдельной папкой `C:\llm\llama.cpp-b10630\`
  (как форк для ternary). Макрос `${server}` не используется. Прод-b9851 не тронут.
- **⚠️ KV-квант только `q4_0` или `q8_0`.** У CUDA flash attention при `head_dim 256`
  нет быстрого кернела для `q5_1`: prefill 1437 → **108 t/s** при здоровой VRAM.
  Выглядит как спилловер, но им не является — подробности в
  [docs/choosing-models.md](../../docs/choosing-models.md#️-тип-kv-кванта-выбирай-из-тех-что-умеет-flash-attention).
- **Конфиг:** `-c 131072 -ub 512 --cache-type-k q4_0 --cache-type-v q4_0`,
  `--ctx-checkpoints 8 --checkpoint-min-step 1024`, `--reasoning-preserve`,
  сэмплинг Qwen thinking-режима `1.0 / 0.95 / 20 / min-p 0`.
  `-ub 1024` даёт всего +4.8% prefill за +208 МиБ буфера — не взяли.
- **Раскладка VRAM:** веса 11671 MiB на GPU + 521 МиБ эмбеддингов в RAM,
  рекуррентное состояние DeltaNet 150 МиБ (от `-c` не зависит), KV@128K 2304 МиБ,
  compute 720 МиБ. Пик под нагрузкой **15467 из 16303**.
- **Длинный контекст не пострадал:** needle-тест 3/3 на 126K токенах.
- **Близнец `qwen3.8-27b-q8kv`** — те же веса, KV в `q8_0`, но контекст 64K
  (`q8_0` вдвое дороже, на 128K нужно было бы ~17.8 ГБ). Брать, если покажется,
  что `q4_0`-кэш подъедает качество на длинном контексте.
- **⚠️ Reasoning по умолчанию `xhigh` — дорогой:** ~1924 токена размышлений и 67.6 с
  против ~224 и 34.3 с у `medium` при сопоставимом ответе. При скупом `max_tokens`
  ответ приходит **пустой** (всё ушло в `reasoning_content`). Позапросно —
  `"chat_template_kwargs": {"reasoning_effort": "medium"}`.
- **Уровней `reasoning_effort` ровно три: `low` / `medium` / `xhigh`** (дефолт `xhigh`) —
  жёстко зашито в jinja-шаблон. Особенности, проверены на живой модели:
  - **`high` — синоним `xhigh`**, а не ступень между `medium` и `xhigh`. Промежуточного
    уровня не существует, шаблон молча переписывает `high` → `xhigh`.
  - Любое другое значение (`none`, `minimal`, да и `LOW` в другом регистре) —
    **HTTP 500**, шаблон кидает `raise_exception`, а не откатывается на дефолт.
    Опечатка в клиентском конфиге положит запрос.
  - Реализовано как подсказка в system-промпте: `xhigh` подставляет «think carefully,
    validate key assumptions…», `low` — «keep your thinking brief…», а **`medium`
    не подставляет ничего** (базовое поведение). Это мягкий стимул, не лимит —
    на сложной задаче порядок по объёму раздумий может и не соблюстись.
  - Совсем без раздумий — `{"enable_thinking": false}`, это отдельный флаг,
    минующий весь блок `reasoning_effort`.
- Не сделано: vision (`mmproj-F16.gguf` не качали), MTP-драфтер (1.37 ГБ — VRAM нет),
  слепое сравнение качества с прод-`qwen3.6-35b-a3b`.
- Полный разбор — [experiments/qwen38-27b-2026-08-26/RESULTS.md](experiments/qwen38-27b-2026-08-26/RESULTS.md).
