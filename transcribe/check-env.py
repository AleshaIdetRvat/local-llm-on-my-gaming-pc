r"""Диагностика окружения на ПК. Гонять после каждого шага установки.

Отдельным файлом, а не `python -c "..."`: цепочка SSH -> PowerShell -> Python
съедает кавычки, и однострочник разваливается на экранировании.

  .\venv\Scripts\python.exe check-env.py
"""

import importlib
import os
import site
import sys


def add_cudnn_to_path():
    """То же, что делает 01-asr.py: CTranslate2 на Windows ищет cuDNN-DLL в PATH,
    а torch везёт свои внутри torch\\lib, где CT2 их не видит."""
    if os.name != "nt":
        return []
    added = []
    for sp in site.getsitepackages():
        nv = os.path.join(sp, "nvidia")
        if not os.path.isdir(nv):
            continue
        for sub in ("cudnn", "cublas"):
            d = os.path.join(nv, sub, "bin")
            if os.path.isdir(d):
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
                added.append(d)
    return added


def line(label, value, ok=None):
    mark = {True: "OK  ", False: "FAIL", None: "    "}[ok]
    print(f"{mark} {label:<22} {value}")


def main():
    print(f"python {sys.version.split()[0]}  {sys.executable}\n")

    added = add_cudnn_to_path()
    for d in added:
        line("cudnn/cublas dll", d, True)
    if os.name == "nt" and not added:
        line("cudnn/cublas dll", "не найдены в site-packages/nvidia", False)

    try:
        import torch
        line("torch", torch.__version__, True)
        line("torch cuda build", torch.version.cuda)
        avail = torch.cuda.is_available()
        line("cuda available", avail, avail)
        if avail:
            cap = torch.cuda.get_device_capability()
            # sm_120 = Blackwell. Если тут не (12, 0) — дальше идти бессмысленно.
            line("compute capability", f"sm_{cap[0]}{cap[1]}", cap == (12, 0))
            line("device", torch.cuda.get_device_name(0))
            free, total = torch.cuda.mem_get_info()
            line("VRAM free/total", f"{free/2**30:.1f} / {total/2**30:.1f} GiB")
    except Exception as e:
        line("torch", f"{type(e).__name__}: {e}", False)

    try:
        import ctranslate2
        line("ctranslate2", ctranslate2.__version__, True)
        n = ctranslate2.get_cuda_device_count()
        line("ct2 cuda devices", n, n > 0)
    except Exception as e:
        line("ctranslate2", f"{type(e).__name__}: {e}", False)

    for mod in ("whisperx", "faster_whisper", "pyannote.audio", "transformers"):
        try:
            m = importlib.import_module(mod)
            line(mod, getattr(m, "__version__", "?"), True)
        except Exception as e:
            line(mod, f"{type(e).__name__}: {e}", False)

    line("HF_TOKEN", "задан" if os.environ.get("HF_TOKEN") else "НЕ задан",
         bool(os.environ.get("HF_TOKEN")))


if __name__ == "__main__":
    main()
