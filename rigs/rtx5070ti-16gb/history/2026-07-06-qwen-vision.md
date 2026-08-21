## 📍 Статус — чекпоинт 2026-07-06: ВКЛЮЧЕНО ЗРЕНИЕ (vision) на Qwen-проде ✅

> **Qwen3.6-35B-A3B теперь принимает картинки на вход.** Причина, почему раньше фото «не отправлялось»: качали **text-only** квант и НЕ грузили vision-проектор — `llama-server` без `--mmproj` картинки молча игнорит (текст работал). Модель multimodal (репо помечен `image-text-to-text`, mmproj есть в `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`).
>
> **Что сделано (по SSH, 2026-07-06):** скачан `mmproj-F16.gguf` (**899 283 584 байта**, байт-точно с HF) в `C:\llm\models\qwen36-35b\`. В `C:\llm\run.bat` добавлено **`--mmproj C:\llm\models\qwen36-35b\mmproj-F16.gguf --no-mmproj-offload`** (энкодер картинок на CPU — чтобы не съесть узкий VRAM-запас). Задача `llama-server` рестартнута. Бэкап прежнего text-only конфига: **`C:\llm\run.bat.bak`**.
>
> **Проверено:** `/v1/models` → `capabilities:[completion, multimodal]`; end-to-end тест (PNG с текстом → OpenAI `image_url` base64 data URI) — модель верно прочитала текст, `finish=stop`. **VRAM 15120 MiB / 16303** (idle даже НИЖЕ прежних ~15.5 ГБ, т.к. проектор на CPU; запас ~1.2 ГБ, спилловера нет). **Задержка на фото:** первый запрос после рестарта ~24с (холодный vision-граф), **тёплый ~2.3с/фото**. Тестовый скрипт: `C:\llm\test-vision.ps1`.
>
> **Откат (обратно на text-only):** вернуть `run.bat.bak` (или убрать два флага `--mmproj`/`--no-mmproj-offload`) + рестарт задачи. **Хочешь быстрее энкодить фото:** убрать `--no-mmproj-offload` (проектор уедет на GPU, +~0.9 ГБ VRAM) — но тогда надо поднять `--n-cpu-moe` 20→~23-24, иначе не влезет (запас всего ~0.8 ГБ был). **Клиент** должен слать картинку в OpenAI-формате: `content` — массив с `{type:"image_url", image_url:{url:"data:image/...;base64,..."}}`.
