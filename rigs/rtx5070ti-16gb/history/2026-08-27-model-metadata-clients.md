## 📍 Статус — чекпоинт 2026-08-27: `capabilities` в config.yaml + клиент pi берёт список моделей из `/v1/models` ✅

> **Что сделано.** Каждой из 9 моделей в `config.yaml` добавлены `name`, `description` и блок
> `capabilities` (`in`/`out`/`tools`/`context`). llama-swap отдаёт это в `/v1/models`, поэтому
> клиенту больше не нужно держать у себя копию списка моделей. На макбуке pi
> (`@earendil-works/pi-coding-agent`) переведён на этот список расширением
> `~/.pi/agent/extensions/rig-models.ts` (шаблон в репо —
> [`templates/pi/models-from-llama-swap.ts`](../../../templates/pi/models-from-llama-swap.ts)).
> Веса, флаги запуска и производительность не трогали — правки чисто описательные.

**Зачем.** В `~/.pi/agent/models.json` руками жили две модели из девяти: список на ноутбуке
разъезжался со стендом при каждом добавлении модели. Теперь источник правды один — `config.yaml`
на ПК, клиент спрашивает сервер на старте.

**Что именно поехало в `/v1/models`** (проверено `curl $RIG_API/models`):
`name`, `description`, `architecture.input_modalities`, `capabilities.function_calling`,
`supported_parameters`, `context_length` и дубль `meta.n_ctx`.

**Контексты в `capabilities.context` — потолок одного запроса, а не значение `-c`:**

| модель | `-c` | `context` | почему |
|---|---|---|---|
| `qwen3.6-35b-a3b` | 102400 | 102400 | `-np 1`, плюс `in: [text, image]` (поднята с `--mmproj`) |
| `glm-4.7-flash`, `glm-4.7-flash-reap-23b` | 131072 | 131072 | `-np 1` |
| `gemma-4-12b-qat` | 65536 | 65536 | `-np 1` |
| `gemma-4-26b-a4b-qat`, `…-nothink` | 32768 | **16384** | `-np 2` → контекст делится на 2 слота |
| `ternary-bonsai-27b` | 102400 | 102400 | `-np 1` |
| `qwen3.8-27b` | 131072 | 131072 | `-np 1` |
| `qwen3.8-27b-q8kv` | 65536 | 65536 | `-np 1` |

**Проверка после копирования конфига** (`scp` зеркала, `--watch-config` подхватил сам,
моделей в VRAM в этот момент не было — reload не мешал):

- `pi --list-models` → все 9 моделей, контексты как в таблице, `images: yes` только у `qwen3.6-35b-a3b`;
- живой запрос `pi -p --provider rig --model gemma-4-12b-qat` → ответ за 13.4 с вместе с холодной загрузкой.

**Грабли.**

- `description` с двоеточием внутри (`"Прод-модель: …"`) ломает YAML, если не закавычить —
  llama-swap просто не примет конфиг. Все `name`/`description` записаны в кавычках.
- Правка скриптом на макбуке перевела файл с CRLF на LF; на ПК уехала та же версия,
  llama-swap её принял без нареканий. Зеркало и ПК сверены по SHA256 — совпадают.
  Отсюда большой diff у `config.yaml` в коммите: содержательных строк ~70.

**Как откатить.**

- Стенд: на ПК лежит `C:\llm\llama-swap\config.yaml.bak-capabilities` (версия до правки) —
  скопировать поверх, `--watch-config` подхватит. В репо — `git revert` правки зеркала.
- Макбук: удалить `~/.pi/agent/extensions/rig-models.ts` и вернуть
  `~/.pi/agent/models.json` из `models.json.bak-static-list` (там прежний ручной список).

**Reasoning у `qwen3.8-27b` (и `-q8kv`) — переключается из pi.** В `/v1/models` таких полей нет
(llama-swap про режимы мышления ничего не знает), поэтому это `modelOverrides` в `models.json`:
`reasoning: true`, `thinkingFormat: "chat-template"` и `chatTemplateKwargs` с
`enable_thinking` + `reasoning_effort`. `thinkingLevelMap` маппит уровни pi на три уровня шаблона:
`low → low`, `medium → medium`, `high → xhigh`; `minimal` / `xhigh` / `max` закрыты (`null`),
чтобы клиент не отправил значение, которого шаблон не знает — оно роняет запрос в HTTP 500.
Мышление выключено → уходит только `enable_thinking: false` (за это отвечает `omitWhenOff`).

Проверка на одном промпте («почему quicksort в среднем O(n log n)»): `--thinking low` — 471 символ
раздумий и 919 выходных токенов, `--thinking high` — 3799 символов и 1723 токена, ответ обоих
раз примерно одного объёма (~2000 символов). `off` / `low` / `medium` / `high` — все четыре
проходят без 500.

**Что осталось на потом.** У остальных моделей (`qwen3.6-35b-a3b`, GLM, Gemma) режим мышления
клиенту по-прежнему не виден — включается тем же способом, когда понадобится.
