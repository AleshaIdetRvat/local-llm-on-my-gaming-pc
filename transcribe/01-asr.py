"""Стадия 1: ASR. wav -> asr.json. Про спикеров ничего не знает.

Запускать на ПК (CUDA). Отдельным процессом от диаризации — так пики VRAM
не складываются, и падение на диаризации не стоит повторного прогона ASR.

  python 01-asr.py call.wav -o asr.json --glossary glossary.json
"""

import argparse
import json
import os
import sys
import time


def add_cudnn_to_path():
    """CTranslate2 на Windows ищет cuDNN-DLL в PATH, а torch везёт свои внутри
    torch\\lib, где CT2 их не видит. Без этого — 'Could not locate cudnn_ops64_9.dll'."""
    if os.name != "nt":
        return
    import site

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
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default="asr.json")
    ap.add_argument("--model", default="large-v3", help="large-v3 | large-v3-turbo")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--compute-type", default="float16",
                    help="int8 падает на sm_120 с CUBLAS_STATUS_NOT_SUPPORTED")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--glossary", default=None)
    ap.add_argument("--align", action="store_true",
                    help="wav2vec2-выравнивание. Русская модель не имеет латиницы в "
                         "словаре — на англотерминах деградирует. Пилот покажет, надо ли.")
    args = ap.parse_args()

    add_cudnn_to_path()
    import torch
    import whisperx

    print(f"torch {torch.__version__} cuda={torch.cuda.is_available()} "
          f"sm={torch.cuda.get_device_capability() if torch.cuda.is_available() else None}",
          flush=True)
    if not torch.cuda.is_available():
        sys.exit("CUDA недоступна — дальше бессмысленно")

    initial_prompt = None
    if args.glossary:
        with open(args.glossary, encoding="utf-8") as f:
            initial_prompt = json.load(f).get("initial_prompt")
        print(f"initial_prompt: {initial_prompt!r}", flush=True)

    t0 = time.time()
    model = whisperx.load_model(
        args.model, device="cuda", compute_type=args.compute_type,
        language=args.language, asr_options={"initial_prompt": initial_prompt},
    )
    # не whisperx.load_audio: он дёргает ffmpeg через subprocess, а на ПК его нет
    from audio_io import load_wav_mono
    audio, sr = load_wav_mono(args.audio)
    dur = len(audio) / sr
    print(f"аудио {dur/3600:.2f} ч, модель загружена за {time.time()-t0:.0f} с", flush=True)

    t1 = time.time()
    result = model.transcribe(audio, batch_size=args.batch_size, print_progress=True)
    print(f"ASR: {time.time()-t1:.0f} с ({dur/(time.time()-t1):.0f}x realtime), "
          f"{len(result['segments'])} сегментов", flush=True)

    del model
    torch.cuda.empty_cache()

    if args.align:
        t2 = time.time()
        model_a, meta = whisperx.load_align_model(
            language_code=result["language"], device="cuda")
        result = whisperx.align(result["segments"], model_a, meta, audio, "cuda",
                                return_char_alignments=False)
        print(f"alignment: {time.time()-t2:.0f} с", flush=True)
        del model_a
        torch.cuda.empty_cache()

    payload = {
        "audio": os.path.abspath(args.audio),
        "duration": dur,
        "model": args.model,
        "aligned": args.align,
        "language": result.get("language", args.language),
        "segments": [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result["segments"]
        ],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"-> {args.out} ({len(payload['segments'])} сегментов, "
          f"всего {time.time()-t0:.0f} с)", flush=True)


if __name__ == "__main__":
    main()
