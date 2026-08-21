# Установка ASR-стека на ПК. Запускать по SSH пошагово, НЕ целиком —
# после установки Python нужен новый сеанс, чтобы подхватился PATH.
#
# Перед началом освободить VRAM: Qwen занимает 14.85 из 16 ГБ.
#   schtasks /End /TN llama-server
#   taskkill /IM llama-swap.exe /F

$ErrorActionPreference = "Stop"
$root = "C:\llm\transcribe"

# --- шаг 1: Python 3.12 (не 3.13 — колёса ctranslate2/onnxruntime отстают) ---
function Step1-Python {
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    Set-Location $root
    curl.exe -L -o py312.exe https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
    # InstallAllUsers=0 — по SSH сессия неэлевейтед, установка для всех упрётся в UAC.
    # Start-Process -Wait обязателен: установщик GUI'шный, PowerShell его не дождётся.
    Start-Process -FilePath .\py312.exe -Wait -ArgumentList `
        "/quiet","InstallAllUsers=0","PrependPath=1","Include_pip=1","Include_test=0"
    Write-Host "Python поставлен. ПЕРЕЗАЙДИ ПО SSH и запусти Step2-Torch." -ForegroundColor Yellow
}

# --- шаг 2: torch с cu128 ПЕРВЫМ, иначе whisperx притащит CPU-сборку ---
function Step2-Torch {
    Set-Location $root
    # per-user установка кладёт Python сюда; launcher `py` в PATH может ещё не быть
    $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    & $py -m venv venv
    .\venv\Scripts\python.exe -m pip install -U pip wheel
    .\venv\Scripts\pip.exe install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

    # контрольная точка: ждём True и (12, 0) = sm_120 (Blackwell)
    .\venv\Scripts\python.exe -c "import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,torch.cuda.is_available(),torch.cuda.get_device_capability())"
    Write-Host "Если выше не True/(12, 0) — дальше идти бессмысленно." -ForegroundColor Yellow
}

# --- шаг 3: whisperx + pyannote ---
function Step3-Whisperx {
    Set-Location $root
    .\venv\Scripts\pip.exe install whisperx
    .\venv\Scripts\pip.exe install "nvidia-cudnn-cu12>=9,<10" nvidia-cublas-cu12

    # whisperx ЖЁСТКО откатывает torch на свой пин (2.8.0) и тянет его с PyPI,
    # а на Windows это CPU-сборка -> cuda.is_available() становится False.
    # Лечится возвратом ТЕХ ЖЕ версий, но из cu128-индекса. Порядок обязателен:
    # только после whisperx, иначе он снова всё перебьёт.
    .\venv\Scripts\pip.exe install --force-reinstall `
        torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 `
        --index-url https://download.pytorch.org/whl/cu128

    .\venv\Scripts\python.exe check-env.py
}

# --- шаг 4: контрольная точка CTranslate2 (самое вероятное место отказа) ---
# CT2 на Windows ищет cuDNN-DLL в PATH, а torch везёт свои внутри torch\lib.
# Симптом провала: "Could not locate cudnn_ops64_9.dll".
function Step4-CheckCT2 {
    Set-Location $root
    $nv = "$root\venv\Lib\site-packages\nvidia"
    $env:PATH = "$nv\cudnn\bin;$nv\cublas\bin;" + $env:PATH
    .\venv\Scripts\python.exe -c "import ctranslate2;print('ctranslate2',ctranslate2.__version__,'cuda-devices',ctranslate2.get_cuda_device_count())"
}

# --- шаг 5: пилот на 10 минутах. Первый запуск дотянет с HF ~3 ГБ весов ---
function Step5-Pilot {
    Set-Location $root
    if (-not $env:HF_TOKEN) { throw "нет HF_TOKEN" }
    $nv = "$root\venv\Lib\site-packages\nvidia"
    $env:PATH = "$nv\cudnn\bin;$nv\cublas\bin;" + $env:PATH
    $env:PYTHONUTF8 = 1   # иначе Windows покорёжит кириллицу в JSON

    .\venv\Scripts\python.exe 01-asr.py pilot_mid.wav -o pilot_asr.json --glossary glossary.json
    .\venv\Scripts\python.exe 02-diarize.py pilot_mid.wav -o pilot_diar.rttm --speakers 3
    .\venv\Scripts\python.exe 03-merge.py --asr pilot_asr.json --rttm pilot_diar.rttm --samples
}

# --- шаг 6: полный прогон ---
function Step6-Full {
    Set-Location $root
    $nv = "$root\venv\Lib\site-packages\nvidia"
    $env:PATH = "$nv\cudnn\bin;$nv\cublas\bin;" + $env:PATH
    $env:PYTHONUTF8 = 1

    .\venv\Scripts\python.exe 01-asr.py call.wav -o asr.json --glossary glossary.json
    .\venv\Scripts\python.exe 02-diarize.py call.wav -o diar.rttm --speakers 3
}

Write-Host @"
Функции загружены. Порядок:
  Step1-Python     потом ПЕРЕЗАЙТИ по SSH
  Step2-Torch      контрольная точка 1: cuda=True, sm=(12, 0)
  Step3-Whisperx
  Step4-CheckCT2   контрольная точка 2: cudnn / CTranslate2
  Step5-Pilot      10 минут, проверить качество ДО полного прогона
  Step6-Full       ~40-60 мин
"@
