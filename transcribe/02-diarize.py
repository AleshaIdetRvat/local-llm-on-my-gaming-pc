"""Стадия 2: диаризация. wav -> diar.rttm.

pyannote напрямую, не через whisperx.diarize — так число спикеров фиксируется
жёстко (num_speakers=3, а не min/max) и виден прогресс.

ВАЖНО: гнать целиком по файлу. Метки SPEAKER_XX локальны для запуска —
склеить диаризацию двух чанков нельзя, SPEAKER_00 в них разные люди.

Веса тянутся с HuggingFace один раз (модели под гейтом — нужен HF_TOKEN и
принятые условия на pyannote/segmentation-3.0 и pyannote/speaker-diarization-3.1).
Дальше всё офлайн, аудио никуда не уходит.

  set HF_TOKEN=hf_...
  python 02-diarize.py call.wav -o diar.rttm --speakers 3
"""

import argparse
import os
import sys
import time



# pyannote.audio 4.x под именем speaker-diarization-3.1 отдаёт сборку, которая
# тянет веса кластеризации из community-1. По названию это не видно — проверяем
# доступ заранее, чтобы не падать через минуту после старта.
GATED_REPOS = [
    ("pyannote/speaker-diarization-3.1", "config.yaml"),
    ("pyannote/segmentation-3.0", "config.yaml"),
    ("pyannote/speaker-diarization-community-1", "config.yaml"),
]


def check_access(token):
    """Проверяет, что все gated-репозитории отдают файлы. Возвращает список закрытых."""
    import urllib.error
    import urllib.request

    blocked = []
    for repo, fname in GATED_REPOS:
        url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                blocked.append(repo)
        except Exception:
            pass  # сеть — не наша забота, упадём позже с внятной ошибкой
    return blocked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default="diar.rttm")
    ap.add_argument("--speakers", type=int, default=3,
                    help="жёсткое число говорящих; 0 = определять автоматически")
    ap.add_argument("--model", default="pyannote/speaker-diarization-3.1")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("нет HF_TOKEN в окружении")

    blocked = check_access(token)
    if blocked:
        print("Не приняты условия использования. Открой под своим аккаунтом и "
              "нажми «Agree and access repository»:")
        for repo in blocked:
            print(f"   https://huggingface.co/{repo}")
        sys.exit(1)

    import numpy as np
    import torch
    from pyannote.audio import Pipeline
    from pyannote.audio.pipelines.utils.hook import ProgressHook

    t0 = time.time()
    # pyannote.audio 4.x переименовал use_auth_token -> token
    try:
        pipeline = Pipeline.from_pretrained(args.model, token=token)
    except TypeError:
        pipeline = Pipeline.from_pretrained(args.model, use_auth_token=token)
    if pipeline is None:
        sys.exit(f"{args.model} не отдалась — прими условия на huggingface.co/{args.model}")
    pipeline.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"пайплайн загружен за {time.time()-t0:.0f} с", flush=True)

    # Читаем сами через stdlib: torchaudio 2.8 декодирует через torchcodec, а тот
    # тянет ffmpeg-DLL, которых на ПК нет. Вход и так 16k mono PCM — тут нечего
    # декодировать. Заодно грузим в память целиком: иначе pyannote перечитывает
    # файл много раз.
    from audio_io import load_wav_mono
    data, sr = load_wav_mono(args.audio)
    waveform = torch.from_numpy(data[None, :])
    print(f"аудио {waveform.shape[1]/sr/3600:.2f} ч, {data.nbytes/2**30:.1f} ГиБ в RAM",
          flush=True)

    kwargs = {} if args.speakers <= 0 else {"num_speakers": args.speakers}
    t1 = time.time()
    with ProgressHook() as hook:
        diar = pipeline({"waveform": waveform, "sample_rate": sr}, hook=hook, **kwargs)
    print(f"диаризация: {time.time()-t1:.0f} с", flush=True)

    # pyannote 4.x возвращает обёртку DiarizeOutput; Annotation лежит внутри
    ann = getattr(diar, "speaker_diarization", diar)

    with open(args.out, "w", encoding="utf-8") as f:
        ann.write_rttm(f)

    stats = {}
    for turn, _, spk in ann.itertracks(yield_label=True):
        stats[spk] = stats.get(spk, 0.0) + turn.duration
    total = sum(stats.values()) or 1.0
    print(f"-> {args.out}")
    for spk, sec in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"   {spk}: {sec/60:6.1f} мин ({sec/total*100:4.1f}%)")


if __name__ == "__main__":
    main()
