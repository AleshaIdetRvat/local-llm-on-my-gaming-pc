## 📍 Статус — чекпоинт 2026-07-08: ПОСТАВЛЕН llama-swap — авто-переключение моделей, читать первым делом ✅

> **⚠️ ВАЖНО — прод теперь идёт через `llama-swap` (proxy), а НЕ напрямую через `llama-server`.** llama-swap слушает `0.0.0.0:8080/v1` и по полю `model` в запросе сам поднимает нужный `llama-server` на внутреннем порту (`${PORT}`, startPort 5800), а предыдущую модель глушит (в 16 ГБ VRAM влезает одна за раз). **Клиенты на макбуке не меняются** — тот же `$RIG_API`, но теперь `model` в запросе ВЫБИРАЕТ модель.
>
> **Модель выбирается полем `model`:** `qwen3.6-35b-a3b` (прод, vision вкл.; **алиас `default`** — стабильное имя для Hermes-агента, при смене прод-модели перевешу алиас, в клиенте менять ничего не надо) · `glm-4.7-flash` (полная) · `glm-4.7-flash-reap-23b`. Проверено с макбука: `/v1/models` отдаёт все три, алиас `default`→qwen работает, горячая замена в обе стороны, всегда ровно 1 процесс `llama-server` (VRAM освобождается при свапе), доступ по LAN ОК. Веб-UI/мониторинг: `http://$RIG_HOST:8080/ui`.
>
> **⚙️ Обновление 2026-07-08 (preserve-thinking на ВСЕХ моделях + сэмплинг Qwen + бенч через llama-swap):**
>
> **`--reasoning-preserve` добавлен ВО ВСЕ ТРИ модели** (qwen + обе GLM — все три template поддерживают preserved-reasoning; GLM это вообще z.ai-модель, флаг ссылается на z.ai docs). Держит reasoning-трейс во всей истории, не только в последнем ходе — по наводке из поста про агентную нестабильность Qwen3.6 («через ~4 хода теряет контекст/зацикливается»). Это серверный аналог `preserve_thinking`. Проверено: все три стартуют healthy с флагом (невалидный аргумент уронил бы старт). ⚠️ **Работает только если КЛИЕНТ (Hermes) возвращает `reasoning_content` обратно в историю сообщений** — серверный флаг необходим, но не достаточен (внутри одного агентного хода/цепочки tool-call'ов сервер сохраняет reasoning сам). Снять: по-запросно `--chat-template-kwargs '{"preserve_thinking": false}'` или убрать из конфига. Про совет из поста «spec-decoding 4-6 черновиков» — неприменимо, у нас spec-decoding в проде выключен (мерили: на нашем MoE-оффлоаде n-max 1 = +11%, 2/3 медленнее).
>
> **Сэмплинг Qwen:** в блок `qwen3.6-35b-a3b` добавлен рекомендованный Qwen сэмплинг **`--temp 0.6 --top-p 0.95 --top-k 20`** (раньше были серверные дефолты). Проверено: `/props` upstream отдаёт temp=0.6/top_p=0.95/top_k=20. Это лишь серверные дефолты — клиенты шлют свои.
>
> **Бенч Qwen через llama-swap (тот же метод, n=9: 3 промпта ~5.7–6.6К × 3 итерации, `/completion`, temp 0, `n_predict=128`, `ignore_eos`, `cache_prompt=false`, 2 полноразмерных прогрева).** Роутинг нативного `/completion` через llama-swap — по пути `/upstream/<model_id>/completion` (без него `/completion` даёт 404, т.к. llama-swap роутит по полю `model`, а в нативном `/completion` его нет). Вывод: **llama-swap оверхеда НЕ добавляет** — pp/tg совпадают с прямым llama-server в пределах шума. Скрипт: `llama-swap/bench-swap.ps1` (на ПК `C:\llm\bench-swap.ps1`).
>
> | Замер (Qwen, n=9) | prefill pp | decode tg |
> |---|---|---|
> | Старый прод (прямой llama-server, baseline) | ~2677 | ~71.7 |
> | Сейчас напрямую в upstream (порт 5802, в обход прокси) | 2664.2 | 72.8 |
> | **Сейчас через llama-swap (8080 → прокси → 5802)** | **2672.4** | **71.0** |
>
> Разница pp <0.5%, tg <2.5% (run-to-run вариация, tg по итерациям 66–73). VRAM qwen через swap 14806–14944 MiB — как раньше.
>
> **Что сделано (по SSH, 2026-07-08):** llama-swap **v236** (`llama-swap.exe`, 25.95 МБ) в `C:\llm\llama-swap\`. Конфиг `C:\llm\llama-swap\config.yaml` — флаги моделей 1:1 из `run.bat`/`run-glm-full.bat`/`run-glm.bat` (см. чекпоинты ниже), отличие только `--host 0.0.0.0 --port 8080` → `--port ${PORT}` и убран redirect в лог. `healthCheckTimeout: 300`, **`globalTTL: 1800`** (авто-выгрузка модели после 30 мин простоя → VRAM освобождается сама под игру; первый запрос после простоя грузит модель ~10-25с), **preload выключен** (после загрузки Windows VRAM=0 до первого запроса). Запуск-обёртка `C:\llm\run-swap.bat` (лог `C:\Users\Public\llama-swap.log`).
>
> **Автозапуск переключён:** задача `llama-server` теперь → `cmd /c C:\llm\run-swap.bat` (была `run.bat`). Проверено: после рестарта задачи llama-swap поднимается сам, боевой запрос через персистентную задачу отвечает. Десктоп-ярлыки обновлены: **`stop-llm.bat`** теперь гасит и `llama-swap.exe`, и `llama-server.exe`; **`start-llm.bat`** — текст под llama-swap. **Файлы Qwen/GLM и все `run*.bat` НЕ тронуты.**
>
> **VRAM (замерено):** idle (модель не загружена) ~556 MiB · `qwen` 14847 · `glm-full` 15947 MiB — совпадает с профилями ниже. **Тайминги:** холодная загрузка модели / свап ~25с (qwen с vision), с прогретым графом быстрее.
>
> **Как менять модели/поведение:** правка `C:\llm\llama-swap\config.yaml` + рестарт задачи (`schtasks /End /TN llama-server; taskkill /IM llama-swap.exe /F; schtasks /Run /TN llama-server`). Добавить модель = новый блок в `models:` (макрос `${server}` = общие флаги). `globalTTL: 0` — держать активную модель в VRAM всегда (как было до llama-swap). Preload при старте = добавить `hooks: {on_startup: {preload: [qwen]}}`.
>
> **Откат на прямой `llama-server` (без свапа):** `$a=New-ScheduledTaskAction -Execute "C:\Windows\System32\cmd.exe" -Argument "/c C:\llm\run.bat"; Set-ScheduledTask -TaskName "llama-server" -Action $a` (или `run-glm-full.bat`/`run-glm.bat`), затем рестарт задачи. `run.bat` и модели на месте — откат мгновенный.
