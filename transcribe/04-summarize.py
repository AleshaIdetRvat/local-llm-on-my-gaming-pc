"""Стадия 4: map-reduce по стенограмме через локальный llama-swap.

Гоняется там же, где агент (адрес API — из rig.local.env); только стандартная библиотека. 4:48 записи ≈ 78k токенов:
формально влезает в 100K-контекст Qwen, но одним запросом не делаем — останется
мало места на ответ, thinking его съест, а качество извлечения фактов у 3B-активной
MoE на такой глубине просядет.

Чанковые выжимки кэшируются на диск: повторный запуск досчитывает недостающее.

  python3 04-summarize.py --turns turns.json --out-dir summary/
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rig  # noqa: E402  — адрес API из rig.local.env

API = rig.api_url() + "/chat/completions"


def hms(sec):
    sec = int(sec)
    return f"{sec//3600}:{sec%3600//60:02d}:{sec%60:02d}"


def call(messages, model="default", thinking=False, max_tokens=2048, timeout=900):
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            ch = data["choices"][0]
            out = (ch["message"].get("content") or "").strip()
            if out:
                return out
            # Пустой content при thinking=True значит, что max_tokens кончились
            # внутри рассуждений и до ответа модель не дошла. Повторяем без
            # thinking: на reduce лучше ответ без размышлений, чем пустота.
            print(f"    ! пустой ответ (finish={ch.get('finish_reason')}) "
                  f"— повтор без thinking", flush=True)
            body["chat_template_kwargs"] = {"enable_thinking": False}
            req = urllib.request.Request(
                API, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer local"})
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            if attempt == 2:
                raise
            print(f"    ! {type(e).__name__}: {e} — повтор через 10 с", flush=True)
            time.sleep(10)


def chunk_turns(turns, window=1200.0, overlap=120.0):
    """Окна по времени с перекрытием, границы — только по репликам (не рвём фразы)."""
    chunks, cur, start = [], [], None
    for t in turns:
        if start is None:
            start = t["start"]
        cur.append(t)
        if t["end"] - start >= window:
            chunks.append(cur)
            tail = [x for x in cur if x["end"] > t["end"] - overlap]
            cur = list(tail)
            start = tail[0]["start"] if tail else None
    if cur and (not chunks or len(cur) > len(
            [x for x in chunks[-1] if x["end"] > chunks[-1][-1]["end"] - overlap])):
        chunks.append(cur)
    return chunks


def render(turns):
    return "\n".join(f"[{hms(t['start'])}] {t['speaker']}: {t['text']}" for t in turns)


MAP_SYS = """Ты обрабатываешь фрагмент стенограммы рабочего созвона.
Извлекай только то, что реально прозвучало. Не додумывай, не обобщай в пустоту.
Если раздел пуст — пиши «—». Каждый пункт снабжай таймкодом из стенограммы."""

MAP_USER = """{gloss}

Фрагмент стенограммы ({t0}–{t1}):

{body}

---
Выдай строго такую структуру:

## Темы
Списком: о чём говорили, с таймкодом начала каждой темы.

## Решения
Что решили окончательно. Формулировка + таймкод.

## Договорённости и задачи
Кто что делает. Формат: «Имя — что делает — срок (если назван) — таймкод».

## Открытые вопросы
Что обсудили, но не закрыли. + таймкод.

## Цифры, названия, ссылки
Конкретика, которая всплыла: суммы, сроки, метрики, имена сервисов."""

OUTLINE_SYS = """Ты собираешь оглавление длинного созвона по выжимкам его фрагментов.
Задача — чтобы человек мог найти нужное место в записи, не переслушивая четыре часа."""

OUTLINE_USER = """Ниже — выжимки по фрагментам созвона длиной {dur}.

{body}

---
Собери оглавление: 10–20 крупных блоков по темам, в хронологии.
Формат строки: `[Ч:ММ:СС] Название блока — одно предложение о чём`.
Соседние фрагменты про одно и то же объединяй в один блок.
Ничего кроме оглавления не пиши."""

SUMMARY_SYS = """Ты сводишь выжимки фрагментов рабочего созвона в один документ.
Убирай дубли: перекрывающиеся фрагменты дают повторы одного и того же.
Противоречия между фрагментами (решение переиграли позже) разрешай в пользу
более позднего таймкода, но упоминай, что решение менялось."""

# Reduce разбит на две половины намеренно. Одним запросом модель расписывала
# «Решения» на 23 пункта, упиралась в max_tokens и обрывалась, не дойдя до
# задач, вопросов и рисков. Поднимать лимит бесполезно — проще дать каждой
# половине отдельный бюджет.
SUMMARY_A_USER = """Ниже — выжимки по фрагментам созвона длиной {dur}. Участники: {speakers}.

{body}

---
Собери две секции, больше ничего:

## Коротко
5–7 предложений: о чём был созвон и к чему пришли.

## Решения
Не более 12 пунктов — только самые значимые, пронумерованно, с таймкодами.
Мелкие детали реализации не перечисляй. Только то, что решено, а не обсуждалось."""

SUMMARY_B_USER = """Ниже — выжимки по фрагментам созвона длиной {dur}.

{body}

---
Собери ОДНУ секцию, больше ничего:

## Задачи

Сгруппируй по направлениям работы (например: прототип и UI, интеграции,
работа с базой кандидатов, продажи и пилоты, юридическое). Заголовок группы —
жирным, под ним список задач.

Правила:
- Объединяй мелкие шаги по одной теме в одну задачу. Не расписывай каждую
  правку отдельно: «поправить отступы», «поменять цвет», «убрать кнопку» —
  это одна задача «доработать UI».
- Формулируй по делу, отглагольно: «Собрать прототип Ракеты», а не
  «обсуждалось, что надо бы собрать».
- В конце каждой задачи — таймкод (или несколько через запятую).
- Срок указывай в скобках, только если он реально прозвучал.
- Имя исполнителя добавляй в скобках ТОЛЬКО если в стенограмме прямо сказано,
  кто берётся. Если не сказано — не приписывай никому.
- Всего не более 25 задач.

"""

SUMMARY_C_USER = """Ниже — выжимки по фрагментам созвона длиной {dur}. Участники: {speakers}.

{body}

---
Собери ОДНУ секцию, больше ничего:

## Открытые вопросы
Что обсудили, но не закрыли, и почему. Не более 10 пунктов.
Каждый пункт — не длиннее двух предложений."""

SUMMARY_D_USER = """Ниже — выжимки по фрагментам созвона длиной {dur}. Участники: {speakers}.

{body}

---
Собери ОДНУ секцию, больше ничего:

## Риски и разногласия
Где участники не сошлись или где звучало беспокойство. Не более 8 пунктов.
Каждый пункт — не длиннее двух предложений."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", default="turns.json")
    ap.add_argument("--glossary", default="glossary.json")
    ap.add_argument("--out-dir", default="summary")
    ap.add_argument("--window", type=float, default=1200.0, help="окно чанка, сек")
    ap.add_argument("--overlap", type=float, default=120.0, help="перекрытие, сек")
    ap.add_argument("--model", default="default")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.turns, encoding="utf-8") as f:
        data = json.load(f)
    turns, dur = data["turns"], data["duration"]

    gloss = {}
    if os.path.exists(args.glossary):
        with open(args.glossary, encoding="utf-8") as f:
            gloss = json.load(f)
    gloss_line = gloss.get("glossary_for_llm", "")
    speakers = ", ".join(sorted({t["speaker"] for t in turns}))

    chunks = chunk_turns(turns, args.window, args.overlap)
    print(f"{hms(dur)} записи -> {len(chunks)} чанков "
          f"(окно {args.window/60:.0f} мин, перекрытие {args.overlap/60:.0f} мин)")

    # --- map: thinking выключен, извлечение фактов механическое ---
    parts = []
    for i, ch in enumerate(chunks):
        path = os.path.join(args.out_dir, f"chunk-{i:02d}.md")
        t0, t1 = hms(ch[0]["start"]), hms(ch[-1]["end"])
        if os.path.exists(path):
            print(f"  [{i+1}/{len(chunks)}] {t0}–{t1}  (из кэша)")
            parts.append(open(path, encoding="utf-8").read())
            continue
        body = render(ch)
        print(f"  [{i+1}/{len(chunks)}] {t0}–{t1}  ~{len(body)//3} ток.", end=" ", flush=True)
        t = time.time()
        out = call([{"role": "system", "content": MAP_SYS},
                    {"role": "user", "content": MAP_USER.format(
                        gloss=gloss_line, t0=t0, t1=t1, body=body)}],
                   model=args.model, thinking=False, max_tokens=2048)
        out = f"### Фрагмент {t0}–{t1}\n\n{out}"
        open(path, "w", encoding="utf-8").write(out)
        parts.append(out)
        print(f"{time.time()-t:.0f} с")

    joined = "\n\n".join(parts)
    print(f"\nвыжимки: ~{len(joined)//3} токенов -> reduce")

    # --- reduce: thinking включён, тут нужно связать и разрешить противоречия ---
    for name, sys_p, usr_p, mt in [
        ("outline.md", OUTLINE_SYS, OUTLINE_USER, 8000),
        ("summary-a.md", SUMMARY_SYS, SUMMARY_A_USER, 6000),
        ("summary-b.md", SUMMARY_SYS, SUMMARY_B_USER, 6000),
        ("summary-c.md", SUMMARY_SYS, SUMMARY_C_USER, 6000),
        ("summary-d.md", SUMMARY_SYS, SUMMARY_D_USER, 6000),
    ]:
        path = os.path.join(args.out_dir, name)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            print(f"  {name} (из кэша)")
            continue
        print(f"  {name}...", end=" ", flush=True)
        t = time.time()
        out = call([{"role": "system", "content": sys_p},
                    {"role": "user", "content": usr_p.format(
                        dur=hms(dur), body=joined, speakers=speakers)}],
                   model=args.model, thinking=True, max_tokens=mt)
        out = re.sub(r"<think>.*?</think>\s*", "", out, flags=re.S).strip()
        open(path, "w", encoding="utf-8").write(out)
        print(f"{time.time()-t:.0f} с")

    # склеиваем половины в один документ
    parts_md = []
    for half in ("summary-a.md", "summary-b.md", "summary-c.md", "summary-d.md"):
        hp = os.path.join(args.out_dir, half)
        if os.path.exists(hp):
            parts_md.append(open(hp, encoding="utf-8").read().strip())
    if parts_md:
        with open(os.path.join(args.out_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(parts_md) + "\n")

    print(f"\n-> {args.out_dir}/outline.md, {args.out_dir}/summary.md")


if __name__ == "__main__":
    main()
