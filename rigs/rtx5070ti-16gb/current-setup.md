# Стенд rtx5070ti-16gb — текущее состояние

> **Железо:** RTX 5070 Ti 16 ГБ · Ryzen 5 7400F (6c/12t) · 32 ГБ DDR5-5600 · Windows 11.
> Режим работы — `RIG_MODE=ssh` (агент на макбуке, ПК управляется по сети).
>
> Обновлено **2026-08-26** (зеркала синхронизированы с ПК по scp в этот же день).
> Модели — [models.md](models.md) · замеры — [benchmarks.md](benchmarks.md) ·
> хронология — [history/](history/) · переносимое знание — [docs/](../../docs/).

## Что работает

**llama-swap v236** (прокси с горячей сменой моделей) на игровом ПК, `C:\llm\llama-swap\`:

- OpenAI-совместимый API: **`$RIG_API`** (ключ — любой непустой).
- Модель выбирается полем `model` в запросе; llama-swap сам поднимает нужный `llama-server`
  на внутреннем порту и глушит предыдущий (в 16 ГБ VRAM живёт одна модель за раз).
- Веб-дашборд: `http://$RIG_HOST:8080/ui`.
- `globalTTL: 1800` — модель выгружается из VRAM после 30 мин простоя (VRAM освобождается
  под игры сама); следующий запрос перегружает её за ~10–30 с.
- `--watch-config` — правки `config.yaml` подхватываются автоматически, рестарт не нужен.

## Модели (9 записей / 7 весов, подробности в [models.md](models.md))

| `model` | Роль | Контекст |
|---|---|---|
| `qwen3.6-35b-a3b` (алиас **`default`**) | **Прод**: код+чат, vision, агентный цикл | 100K |
| `gemma-4-26b-a4b-qat` | Быстрейшая ≤32K, `-np 2` (2 параллельных × 16K) | 32K |
| `gemma-4-26b-a4b-qat-nothink` | Она же без reasoning (`enable_thinking=false`) | 32K |
| `gemma-4-12b-qat` | Средний контекст, целиком на GPU | 64K |
| `glm-4.7-flash` | Полное качество GLM (все 64 эксперта) | 128K |
| `glm-4.7-flash-reap-23b` | GLM быстрее (REAP-прун, near-lossless) | 128K |
| `ternary-bonsai-27b` | Эксперимент: BitNet 27B в 7.17 ГБ (форк llama.cpp) | 100K |
| `qwen3.8-27b` | Самая свежая: dense 27B, гибридная attention (билд b10630) | 128K |
| `qwen3.8-27b-q8kv` | Она же с KV в `q8_0` (точнее кэш, меньше контекст) | 64K |

Алиас `default` — стабильное имя для клиентов (Hermes и др.): при смене прод-модели
перевешивается алиас в конфиге, клиенты не трогаются.

## Автозапуск

Задача планировщика **`llama-server`**: принципал `llm` (S4U, RunLevel Highest),
действие `cmd /c C:\llm\run-swap.bat`, `MultipleInstancesPolicy=IgnoreNew`, RestartCount 3.
Триггеры — **два**: At Startup (настоящий Restart) **и** At Logon (обычное включение —
Fast Startup не даёт BootTrigger сработать, см. [windows-notes.md](../../docs/windows-notes.md#fast-startup-ломает-автозапуск)).

Ярлыки на интерактивном десктопе: **«LLM — включить/выключить»** (`start-llm.bat` / `stop-llm.bat`,
самоповышаются через UAC; stop гасит и llama-swap, и llama-server → освобождает VRAM под игру).

## Как поменять конфиг моделей

1. Правишь [`pc-mirrors/config.yaml`](pc-mirrors/config.yaml) в репо.
2. `scp -i $RIG_SSH_KEY pc-mirrors/config.yaml "$RIG_SSH_USER@$RIG_HOST:C:/llm/llama-swap/config.yaml"`
3. Всё — `--watch-config` подхватит сам. Проверка: `curl $RIG_API/models`.

Добавить модель = новый блок в `models:` (макрос `${server}` — общие флаги; ternary — свой exe
форка, макрос не использует). На ПК лежат бэкапы прежних версий: `config.yaml.bak*`.

## Управление задачей (по SSH)

```powershell
schtasks /Run /TN llama-server    # поднять
schtasks /End /TN llama-server    # погасить задачу
taskkill /IM llama-swap.exe /F    # добить процесс (при полном рестарте)
Get-ScheduledTask llama-server | Get-ScheduledTaskInfo
```

Полный рестарт: `schtasks /End /TN llama-server; taskkill /IM llama-swap.exe /F; schtasks /Run /TN llama-server`.

## Раскладка на ПК (`C:\llm\`)

| Путь | Что |
|---|---|
| `llama.cpp\` | Сток llama.cpp **b9851**, пребилт cuda-13.3 (прод-бинарь) |
| `llama.cpp-prism\` | Форк PrismML `prism-b9591` cuda-12.4 — только для ternary-bonsai |
| `llama.cpp-b10630\` | Сток **b10630** cuda-13.3 — только для `qwen3.8-27b*` (cudart-DLL скопированы из `llama.cpp\`) |
| `llama-swap\` | llama-swap.exe v236 + `config.yaml` (зеркало → `pc-mirrors/`) |
| `models\qwen36-35b\` · `glm47-flash-full\` · `glm47-flash-reap-23b\` · `gemma4-12b-qat\` · `gemma4-26b-a4b-qat\` · `ternary-bonsai-27b\` · `qwen38-27b\` | GGUF-файлы моделей |
| `run-swap.bat` | Запуск llama-swap (его дёргает задача автозапуска; зеркало → `pc-mirrors/`) |
| `run.bat`, `run-glm*.bat` | Прямой запуск llama-server без свапа (откат; `run.bat` ↔ `pc-mirrors/run-qwen.*`) |
| `bench-*.ps1`, `test-vision.ps1` | Локальные скрипты замеров на ПК |
| `C:\Users\Public\llama-swap.log` (и `llama-server*.log`) | Логи |

## Откат на прямой llama-server (без свапа)

```powershell
$a = New-ScheduledTaskAction -Execute "C:\Windows\System32\cmd.exe" -Argument "/c C:\llm\run.bat"
Set-ScheduledTask -TaskName "llama-server" -Action $a
schtasks /End /TN llama-server; taskkill /IM llama-swap.exe /F; schtasks /Run /TN llama-server
```

(`run.bat` = Qwen напрямую; `run-glm-full.bat` / `run-glm.bat` — GLM-варианты.)

## Незакрытые хвосты (по желанию)

- **Ternary-Bonsai:** честный свип `bench-ctx.py` не гонялся (только проба ~64 tok/s);
  драфтер `dspark-Q4_1` для спекулятивного декода не пробовали; vision (mmproj) не качали;
  оценка качества юзером не делалась. Контекст поднят 32K → 100K (запас VRAM был ~7 ГБ).
- **Repetition-loop на gemma-26b** (инцидент 2026-07-10): DRY-сэмплер — кандидат-фикс,
  **не внедрён**; рекомендованный порядок фиксов — в [чекпоинте](history/2026-07-10-parallel-np2-incident.md).
- **Проверка BootTrigger** после настоящего Restart (LogonTrigger уже проверен в бою).
