#!/usr/bin/env python3
"""
rig.py — параметры стенда для скриптов репо.

Читает KEY=value из rig.local.env рядом с этим файлом (шаблон — rig.example.env).
Переменные окружения приоритетнее файла, так что разовый прогон по другому адресу
делается без правки конфига:

    RIG_API=http://192.168.1.50:8080/v1 python3 bench/bench-ctx.py

Смысл модуля — спрятать разницу между двумя режимами работы (RIG_MODE):
команда к видеокарте в local-режиме идёт в локальный PowerShell, а в ssh-режиме
заворачивается в ssh. Всё остальное в скриптах одинаково.
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / "rig.local.env"

_HINT = (
    f"нет {ENV_FILE.name} — скопируй шаблон и заполни под свой стенд:\n"
    f"    cp {ENV_FILE.with_name('rig.example.env')} {ENV_FILE}\n"
    f"или попроси агента: «настрой стенд» (скилл rig-setup)"
)


def load():
    """Параметры стенда: файл rig.local.env, поверх него — переменные окружения."""
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()
    for key in list(cfg) + ["RIG_NAME", "RIG_MODE", "RIG_API", "RIG_ROOT",
                            "RIG_HOST", "RIG_SSH_USER", "RIG_SSH_KEY",
                            "RIG_HOSTNAME", "RIG_WIFI_SSID"]:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def get(key, default=None):
    value = load().get(key) or default
    if value is None:
        raise SystemExit(f"{key} не задан. {_HINT}")
    return value


def api_base():
    """Корень HTTP-API llama-swap БЕЗ /v1 — нативные эндпоинты живут вне /v1."""
    base = get("RIG_API").rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def api_url():
    """Полный OpenAI-совместимый базовый URL, с /v1."""
    return api_base() + "/v1"


def pc_cmd(powershell):
    """argv для запуска PowerShell-команды на ПК с видеокартой.

    local: агент уже на этом ПК — зовём powershell напрямую.
    ssh:   агент на другой машине — тот же текст команды уезжает по ssh.
    Текст команды в обоих случаях один и тот же, поэтому процедуры в доках
    пишутся один раз, без развилки на каждый чих.
    """
    cfg = load()
    mode = cfg.get("RIG_MODE", "local")
    if mode == "local":
        return ["powershell", "-NoProfile", "-Command", powershell]
    if mode != "ssh":
        raise SystemExit(f"RIG_MODE={mode!r}: ожидается local или ssh. {_HINT}")
    key = Path(os.path.expanduser(get("RIG_SSH_KEY")))
    return ["ssh", "-i", str(key), "-o", "BatchMode=yes",
            f"{get('RIG_SSH_USER')}@{get('RIG_HOST')}", powershell]


def pc_run(powershell, timeout=30):
    """Выполнить команду на ПК и вернуть stdout строкой ('' при любой осечке).

    Осечка не роняет замер: VRAM — справочная колонка, а не результат бенча.
    """
    try:
        out = subprocess.run(pc_cmd(powershell), capture_output=True,
                             text=True, timeout=timeout)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError, SystemExit):
        return ""


def vram_used_mib():
    """Занятая VRAM в MiB, 0 если снять не удалось.

    Мерить надо ВО ВРЕМЯ генерации: в простое WDDM вытесняет память процесса
    в RAM и цифра получается бессмысленно низкой.
    """
    out = pc_run("nvidia-smi --query-gpu=memory.used "
                 "--format=csv,noheader,nounits")
    digits = "".join(c for c in out.splitlines()[0] if c.isdigit()) if out else ""
    return int(digits) if digits else 0


if __name__ == "__main__":
    cfg = load()
    if not cfg:
        raise SystemExit(_HINT)
    for key in sorted(cfg):
        print(f"{key}={cfg[key]}")
    print(f"\napi_base() = {api_base()}")
    print(f"pc_cmd()   = {' '.join(pc_cmd('nvidia-smi -L'))}")
