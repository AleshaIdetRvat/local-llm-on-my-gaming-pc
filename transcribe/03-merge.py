"""Стадия 3: мерж ASR + диаризации -> transcript.md + turns.json.

Чистый Python, секунды. Переигрывается сколько угодно раз — все решения
(имена спикеров, словарь замен, пороги склейки) правятся здесь, без ASR.

Опознание спикеров — в два шага:
  python 03-merge.py --samples          # выдаст характерные реплики каждого
  python 03-merge.py --map SPEAKER_00=Лёша SPEAKER_01=Федя SPEAKER_02=Женя
"""

import argparse
import json
import os
import re
from collections import defaultdict


def hms(sec):
    sec = int(sec)
    return f"{sec//3600}:{sec%3600//60:02d}:{sec%60:02d}"


def read_rttm(path):
    """RTTM: SPEAKER <file> 1 <start> <dur> <NA> <NA> <speaker> <NA> <NA>"""
    turns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.split()
            if len(p) >= 8 and p[0] == "SPEAKER":
                start, dur = float(p[3]), float(p[4])
                turns.append((start, start + dur, p[7]))
    return sorted(turns)


def assign_speaker(seg_start, seg_end, turns):
    """Спикер с максимальным перекрытием. Работает и без word-level выравнивания."""
    best, best_ov = None, 0.0
    for t_start, t_end, spk in turns:
        if t_start >= seg_end:
            break
        ov = min(seg_end, t_end) - max(seg_start, t_start)
        if ov > best_ov:
            best, best_ov = spk, ov
    return best


def norm(text):
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


# Whisper large-v3 обучался на субтитрах и на тишине/шуме выдаёт титры
# переводчиков. Это не речь — выкидываем целиком, а не схлопываем.
HALLUCINATIONS = [
    r"субтитры\s+(создавал|делал|подготовил|сделал)",
    r"субтитр\w*\s+@?\w*torzok",
    r"редактор\s+субтитров",
    r"корректор\s+\w\.",
    r"продолжение\s+следует",
    r"^\W*спасибо\s+за\s+просмотр\W*$",
    r"^\W*подписывайтесь\s+на\s+канал\W*$",
    r"^\W*(ссылка|ссылки)\s+в\s+описании\W*$",
]
_HALL_RE = [re.compile(p, re.IGNORECASE) for p in HALLUCINATIONS]


def drop_hallucinations(segments):
    """Выбрасывает сегменты, целиком состоящие из титров-галлюцинаций."""
    kept, dropped = [], []
    for seg in segments:
        t = seg["text"].strip()
        # снимаем повтор одной и той же фразы внутри сегмента перед проверкой
        probe = norm(t)
        if any(r.search(probe) for r in _HALL_RE) and len(t) < 400:
            dropped.append(seg)
        else:
            kept.append(seg)
    return kept, dropped


def drop_loops(segments, threshold=3):
    """Whisper на однородном звуке залипает и повторяет фразу десятки раз.
    Схлопываем цепочки одинаковых подряд идущих сегментов."""
    out, run = [], []

    def flush():
        if not run:
            return
        if len(run) >= threshold:
            first = dict(run[0])
            first["end"] = run[-1]["end"]
            first["text"] = first["text"] + f"  [×{len(run)}, похоже на залипание]"
            out.append(first)
        else:
            out.extend(run)

    for seg in segments:
        if run and norm(seg["text"]) == norm(run[-1]["text"]) and norm(seg["text"]):
            run.append(seg)
        else:
            flush()
            run = [seg]
    flush()
    return out


def apply_replacements(text, patterns):
    for pat, repl in patterns:
        text = pat.sub(repl, text)
    return text


def split_by_words(segments, rttm):
    """Режет сегменты по границам смены спикера, опираясь на пословные таймкоды.

    Без этого весь 25-секундный кусок Whisper уходит одному спикеру, хотя
    диаризация различает отрезки по ~2 с: на реальном прогоне 72% сегментов
    содержали двух-трёх говорящих, 16% речи уходило не тому.

    Слова без таймкода (латиница вне словаря wav2vec2) прилипают к предыдущему.
    """
    out = []
    for seg in segments:
        words = seg.get("words") or []
        if not words:
            out.append(dict(seg, speaker=assign_speaker(seg["start"], seg["end"], rttm)))
            continue

        cur = None
        for w in words:
            if "start" not in w:
                if cur:
                    cur["text"] += w["w"] if w["w"].startswith(" ") else " " + w["w"]
                continue
            spk = assign_speaker(w["start"], w["end"], rttm)
            if cur and cur["speaker"] == spk:
                cur["end"] = w["end"]
                cur["text"] += w["w"] if w["w"].startswith(" ") else " " + w["w"]
            else:
                if cur:
                    out.append(cur)
                cur = {"start": w["start"], "end": w["end"],
                       "text": w["w"].strip(), "speaker": spk}
        if cur:
            out.append(cur)
    return out


def smooth_speakers(pieces, max_words=3, max_pause=0.35):
    """Возвращает хвосты фраз, улетевшие к чужому спикеру.

    На границах реплик диаризация шумит, и последнее слово фразы отрывается
    соседу: «...потому что логика вообще» | «другая.»

    Критерий — пауза, а не длительность. Хвост примыкает к своей фразе вплотную
    (0.0-0.1 с), тогда как настоящая короткая реплика («Пока меня не было»)
    начинается после заметной тишины. По длительности не отличить: wav2vec2
    растягивает таймкод последнего слова на всю следующую паузу, и «есть.»
    из одного слова выходит длиной 4.5 с.
    """
    fixed = 0
    for i in range(1, len(pieces)):
        prev, cur = pieces[i - 1], pieces[i]
        if cur["speaker"] == prev["speaker"]:
            continue
        if len(cur["text"].split()) <= max_words \
                and cur["start"] - prev["end"] <= max_pause:
            cur["speaker"] = prev["speaker"]
            fixed += 1
    return pieces, fixed


def build_turns(segments, rttm, gap=2.0, max_turn=120.0):
    """Склейка подряд идущих сегментов одного спикера в реплики.

    Без rttm (диаризация ещё не готова) склеиваем просто по паузам — стенограмма
    и выжимка по таймкодам от спикеров не зависят.

    max_turn режет длинные монологи на абзацы: иначе без диаризации всё
    склеивается в простыни по шесть минут, которые невозможно читать.
    """
    if rttm and any(s.get("words") for s in segments):
        segments = split_by_words(segments, rttm)   # пословно — точные границы
        segments, fixed = smooth_speakers(segments)
        if fixed:
            print(f"сглажено обрывков на границах: {fixed}")

    turns = []
    for seg in segments:
        if not rttm:
            spk = "—"
        elif "speaker" in seg:
            spk = seg["speaker"] or "SPEAKER_?"
        else:
            spk = assign_speaker(seg["start"], seg["end"], rttm) or "SPEAKER_?"
        if turns and turns[-1]["speaker"] == spk \
                and seg["start"] - turns[-1]["end"] <= gap \
                and seg["end"] - turns[-1]["start"] <= max_turn:
            turns[-1]["end"] = seg["end"]
            turns[-1]["text"] += " " + seg["text"]
        else:
            turns.append({"start": seg["start"], "end": seg["end"],
                          "speaker": spk, "text": seg["text"]})
    return turns


def print_samples(turns, per_speaker=6):
    """Характерные реплики каждого спикера — чтобы человек опознал, кто есть кто.
    Надёжнее, чем поручать это LLM."""
    by_spk = defaultdict(list)
    for t in turns:
        wc = len(t["text"].split())
        if 8 <= wc <= 40:
            by_spk[t["speaker"]].append(t)
    for spk in sorted(by_spk):
        items = by_spk[spk]
        total = sum(t["end"] - t["start"] for t in turns if t["speaker"] == spk)
        print(f"\n=== {spk} — {total/60:.1f} мин речи, {len(items)} реплик-кандидатов ===")
        step = max(1, len(items) // per_speaker)
        for t in items[::step][:per_speaker]:
            print(f"  [{hms(t['start'])}] {t['text']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default="asr.json")
    ap.add_argument("--rttm", default="diar.rttm")
    ap.add_argument("--glossary", default="glossary.json")
    ap.add_argument("--out-md", default="transcript.md")
    ap.add_argument("--out-json", default="turns.json")
    ap.add_argument("--samples", action="store_true",
                    help="показать характерные реплики каждого спикера и выйти")
    ap.add_argument("--map", nargs="*", default=[],
                    metavar="SPEAKER_00=Имя", help="переименование спикеров")
    ap.add_argument("--gap", type=float, default=2.0,
                    help="пауза, до которой реплики одного спикера склеиваются")
    ap.add_argument("--max-turn", type=float, default=120.0,
                    help="максимальная длина склеенной реплики, сек")
    args = ap.parse_args()

    with open(args.asr, encoding="utf-8") as f:
        asr = json.load(f)

    if os.path.exists(args.rttm):
        rttm = read_rttm(args.rttm)
    else:
        rttm = []
        print(f"! {args.rttm} нет — собираю без разделения по голосам")

    with open(args.glossary, encoding="utf-8") as f:
        gloss = json.load(f)
    repl = gloss.get("replacements", {})
    # сначала опечатки, следом — нормализация регистра: Whisper напишет "хантфлоу"
    # строчными, канонический вид — "Хантфлоу". Список canonical держим вручную:
    # автоматически брать все значения нельзя, там есть слова-омонимы.
    canon = list(dict.fromkeys(list(repl.values()) + gloss.get("canonical", [])))
    patterns = [
        (re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE), v)
        for k, v in list(repl.items()) + [(c, c) for c in canon]
    ]

    segments, hallucinated = drop_hallucinations(asr["segments"])
    segments = drop_loops(segments)
    dropped = len(asr["segments"]) - len(hallucinated) - len(segments)
    if hallucinated:
        print(f"выброшено галлюцинаций: {len(hallucinated)}")
        for seg in hallucinated[:5]:
            print(f"   [{hms(seg['start'])}] {seg['text'][:70]}")
    for seg in segments:
        seg["text"] = apply_replacements(seg["text"], patterns)

    turns = build_turns(segments, rttm, gap=args.gap, max_turn=args.max_turn)

    if args.samples:
        print_samples(turns)
        return

    names = dict(m.split("=", 1) for m in args.map)
    for t in turns:
        t["speaker"] = names.get(t["speaker"], t["speaker"])

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"duration": asr["duration"], "turns": turns}, f,
                  ensure_ascii=False, indent=1)

    talk = defaultdict(float)
    for t in turns:
        talk[t["speaker"]] += t["end"] - t["start"]

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(f"# Стенограмма\n\n")
        f.write(f"> {hms(asr['duration'])} · модель `{asr['model']}` · "
                f"{len(turns)} реплик")
        if dropped:
            f.write(f" · схлопнуто {dropped} повторов")
        f.write("\n>\n")
        for spk, sec in sorted(talk.items(), key=lambda x: -x[1]):
            f.write(f"> **{spk}** — {sec/60:.0f} мин\n")
        f.write("\n---\n\n")
        for t in turns:
            f.write(f"**[{hms(t['start'])}] {t['speaker']}:** {t['text']}\n\n")

    print(f"-> {args.out_md}, {args.out_json}  ({len(turns)} реплик, "
          f"схлопнуто повторов: {dropped})")
    for spk, sec in sorted(talk.items(), key=lambda x: -x[1]):
        print(f"   {spk}: {sec/60:.1f} мин")


if __name__ == "__main__":
    main()
