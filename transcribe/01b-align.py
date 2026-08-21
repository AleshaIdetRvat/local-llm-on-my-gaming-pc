"""Стадия 1b: выравнивание по словам. asr.json -> asr_aligned.json.

Зачем: Whisper режет речь на куски по 20-30 с, а диаризация работает с
разрешением ~2 с. Без пословных таймкодов приходится приписывать весь кусок
одному спикеру — на реальном прогоне так вышло 72% кусков с двумя-тремя
говорящими внутри и 16% речи, приписанной не тому.

wav2vec2 выдаёт таймкод каждому слову, и тогда спикер назначается пословно.

Whisper перегонять не нужно — работаем поверх готового asr.json.

  python 01b-align.py --asr asr.json --audio call.wav -o asr_aligned.json
"""

import argparse
import json
import os
import site
import sys
import time


def add_cudnn_to_path():
    if os.name != "nt":
        return
    for sp in site.getsitepackages():
        nv = os.path.join(sp, "nvidia")
        if not os.path.isdir(nv):
            continue
        for sub in ("cudnn", "cublas"):
            d = os.path.join(nv, sub, "bin")
            if os.path.isdir(d):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default="asr.json")
    ap.add_argument("--audio", default="call.wav")
    ap.add_argument("-o", "--out", default="asr_aligned.json")
    args = ap.parse_args()

    add_cudnn_to_path()
    import torch
    import whisperx
    from audio_io import load_wav_mono

    with open(args.asr, encoding="utf-8") as f:
        asr = json.load(f)
    audio, sr = load_wav_mono(args.audio)
    lang = asr.get("language", "ru")
    print(f"{len(asr['segments'])} сегментов, {len(audio)/sr/3600:.2f} ч, язык {lang}",
          flush=True)

    t0 = time.time()
    model_a, meta = whisperx.load_align_model(language_code=lang, device="cuda")
    print(f"модель выравнивания загружена за {time.time()-t0:.0f} с", flush=True)

    t1 = time.time()
    res = whisperx.align(asr["segments"], model_a, meta, audio, "cuda",
                         return_char_alignments=False, print_progress=True)
    print(f"выравнивание: {time.time()-t1:.0f} с", flush=True)
    del model_a
    torch.cuda.empty_cache()

    # Слова без таймкода — те, что не легли на словарь wav2vec2 (латиница в
    # русской модели). Оставляем как есть: спикера им назначим по соседям.
    segments, words_total, words_timed = [], 0, 0
    for s in res["segments"]:
        words = []
        for w in s.get("words", []):
            words_total += 1
            if "start" in w and "end" in w:
                words_timed += 1
                words.append({"w": w["word"], "start": w["start"], "end": w["end"]})
            else:
                words.append({"w": w["word"]})
        segments.append({"start": s["start"], "end": s["end"],
                         "text": s["text"].strip(), "words": words})

    payload = dict(asr)
    payload["segments"] = segments
    payload["aligned"] = True
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    pct = words_timed / words_total * 100 if words_total else 0
    print(f"-> {args.out}: {words_total} слов, с таймкодом {words_timed} ({pct:.1f}%)")
    if pct < 90:
        print("  ! много слов без таймкода — вероятно, латиница вне словаря модели")


if __name__ == "__main__":
    main()
