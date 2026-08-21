r"""Чтение WAV без ffmpeg и без torchaudio.

На ПК нет ffmpeg, а обе библиотеки на него завязаны:
  - whisperx.load_audio дёргает ffmpeg через subprocess -> FileNotFoundError;
  - torchaudio 2.8 декодирует через torchcodec, который на Windows не грузится
    без ffmpeg-DLL.

Вход в пайплайне всегда 16 кГц mono PCM (ffmpeg отработал на маке), так что
декодировать нечего — хватает stdlib `wave`.
"""

import sys
import wave

import numpy as np

TARGET_SR = 16000


def load_wav_mono(path, expect_sr=TARGET_SR):
    """PCM WAV -> (float32 ndarray [samples], sample_rate). Стерео сводится в моно."""
    with wave.open(path, "rb") as w:
        width, sr, ch, n = (w.getsampwidth(), w.getframerate(),
                            w.getnchannels(), w.getnframes())
        raw = w.readframes(n)

    if width != 2:
        sys.exit(f"{path}: ожидался 16-битный PCM, а тут {width * 8} бит")
    if expect_sr and sr != expect_sr:
        sys.exit(f"{path}: ожидалось {expect_sr} Гц, а тут {sr}. "
                 f"Пересобери: ffmpeg -i ... -ac 1 -ar {expect_sr} -c:a pcm_s16le")

    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr
