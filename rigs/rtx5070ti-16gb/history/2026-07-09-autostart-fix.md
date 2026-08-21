## 📍 Статус — чекпоинт 2026-07-09: ПОЧИНЕН АВТОЗАПУСК — Fast Startup ломал BootTrigger, добавлен LogonTrigger ✅

> **⚠️ Симптом (юзер, 09.07):** включил ПК, через ~5 мин `curl $RIG_API/models` → `couldn't connect / timeout`. Автозапуск не поднял сервер после обычного включения.
>
> **Диагноз:** задача `llama-server` (S4U от `llm` → `C:\llm\run-swap.bat` → llama-swap на `:8080`) имела единственный триггер `<BootTrigger />` («At Startup»). На ПК включён **Fast Startup** (`HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power` → `HiberbootEnabled=1`). Обычное «Завершение работы» → включение идёт как **резюм из гибернации ядра, а НЕ настоящий boot** → `BootTrigger` НЕ срабатывает (на настоящем Restart сработал бы). Проверено по факту: задача в состоянии `Ready` со вчерашним `LastRunTime` (08.07 17:11), процессов llama-swap нет, порт 8080 пуст.
>
> **Фикс (по выбору юзера — не трогать Fast Startup):** к задаче добавлен второй триггер `<LogonTrigger />` (фактически `<desktop-user>` всегда логинится после включения → сервер встаёт при логине). `BootTrigger` оставлен для настоящих Restart (сработает до логина). `MultipleInstancesPolicy=IgnoreNew` не даёт запуститься дважды, если сработают оба. Команда (S4U-задача меняется без пароля `llm`):
> ```powershell
> $boot = New-ScheduledTaskTrigger -AtStartup
> $logon = New-ScheduledTaskTrigger -AtLogOn
> Set-ScheduledTask -TaskName "llama-server" -Trigger @($boot,$logon)
> ```
> Проверено: XML задачи показывает оба триггера; сервер поднят вручную (`schtasks /Run /TN llama-server`, PID процесса llama-swap с `--watch-config`), `/v1/models` с макбука отдаёт все 5 моделей. Починку в бою подтвердит следующий цикл выключить→включить (или Restart для проверки BootTrigger до логина).
>
> **Альтернатива фиксу (не выбрана):** отключить Fast Startup (`HiberbootEnabled=0`) → BootTrigger работает всегда, но холодный boot чуть медленнее.
>
> **➕ Заодно (09.07) устранён дрейф десктоп-ярлыков от llama-swap:** (1) `run-swap.bat` (что запускает задача/ярлык «включить») стартовал llama-swap **без `--watch-config`**, хотя живой процесс крутился с ним → добавлен флаг, чтобы ярлык давал тот же авто-подхват правок `config.yaml`; (2) в подсказке `start-llm.bat` обновлён список моделей (`qwen / glm-full / glm-reap` → все 5: обе геммы + qwen + обе GLM). Бэкапы: `run-swap.bat.bak`, `start-llm.bat.bak`.
