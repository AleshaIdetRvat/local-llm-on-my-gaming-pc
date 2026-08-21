#!/usr/bin/env python3
"""
bench-ctx.py — context-length sweep benchmark through llama-swap.

Measures prefill (pp) and decode (tg) tok/s at several context depths for one or
more models, hitting the native /completion endpoint via llama-swap's
/upstream/<model_id>/ route (same method as bench-swap.ps1, cache_prompt=false).

This mirrors what `llama-bench -d <depths>` does (the community-standard way to
see decode degradation as KV grows), but through the LIVE served config so the
numbers match production 1:1 and are comparable to our historical tables.

Адрес API и способ снять VRAM берутся из rig.local.env (см. rig.py), поэтому
скрипт одинаково работает и с другой машины по SSH, и прямо на самом ПК:
    python3 bench/bench-ctx.py
"""
import json, time, urllib.request, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rig  # noqa: E402  — параметры стенда из rig.local.env

HOST = rig.api_base()
ITERS  = 3
NPRED  = 96
TIMEOUT = 300

# ~18 tokens per repeat of this sentence (calibrated: x350 -> prompt_n 6301).
BASE = ("The quick brown fox jumps over the lazy dog and then keeps running "
        "through the quiet forest. ")
TOK_PER_REPEAT = 18.0

# model_id -> usable context ceiling (from config.yaml -c). Sizes above are skipped.
MODELS = {
    "ternary-bonsai-27b":  102400,
    "gemma-4-12b-qat":     65536,
    "gemma-4-26b-a4b-qat": 32768,
    "qwen3.6-35b-a3b":     102400,
}
# target context depths in tokens
SIZES = [2000, 8000, 32000, 60000, 96000]


def post(path, body):
    req = urllib.request.Request(HOST + path,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def vram():
    return rig.vram_used_mib()


def bench_model(model):
    upstream = f"/upstream/{model}"
    ceil = MODELS[model]
    print(f"\n{'='*72}\n### {model}   (ctx ceiling {ceil})\n{'='*72}")
    print(f"{'target':>7} {'prompt_n':>9} {'pp tok/s':>10} {'tg tok/s':>10}")
    rows = []
    peak_vram = 0
    for target in SIZES:
        if target + NPRED > ceil * 0.98:
            continue
        reps = max(1, round(target / TOK_PER_REPEAT))
        prompt = BASE * reps
        # warmup at this size (graph/alloc), discarded
        try:
            post(f"{upstream}/completion",
                 {"prompt": prompt, "n_predict": 16, "temperature": 0,
                  "cache_prompt": False, "ignore_eos": True})
        except Exception as e:
            print(f"  warmup {target} failed: {e}")
            continue
        pp, tg, pn = [], [], 0
        for _ in range(ITERS):
            r = post(f"{upstream}/completion",
                     {"prompt": prompt, "n_predict": NPRED, "temperature": 0,
                      "cache_prompt": False, "ignore_eos": True})
            t = r["timings"]
            pn = t["prompt_n"]
            pp.append(t["prompt_per_second"])
            tg.append(t["predicted_per_second"])
        ppa = sum(pp) / len(pp)
        tga = sum(tg) / len(tg)
        v = vram()
        peak_vram = max(peak_vram, v)
        rows.append({"target": target, "prompt_n": pn,
                     "pp": round(ppa, 1), "tg": round(tga, 1), "vram": v})
        print(f"{target:>7} {pn:>9} {ppa:>10.1f} {tga:>10.1f}   vram={v}")
    print(f"  peak VRAM (MiB): {peak_vram}")
    return {"model": model, "peak_vram": peak_vram, "rows": rows}


def main():
    models = sys.argv[1:] or list(MODELS.keys())
    t0 = time.time()
    results = [bench_model(m) for m in models]
    print(f"\n{'='*72}\nSUMMARY (pp / tg tok/s by context depth)\n{'='*72}")
    for res in results:
        print(f"\n{res['model']}  (peak VRAM {res['peak_vram']} MiB)")
        for r in res["rows"]:
            print(f"  ~{r['target']//1000}K (n={r['prompt_n']}): "
                  f"pp={r['pp']}  tg={r['tg']}")
    print(f"\ndone in {round(time.time()-t0)}s")
    with open("bench-ctx-results.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
