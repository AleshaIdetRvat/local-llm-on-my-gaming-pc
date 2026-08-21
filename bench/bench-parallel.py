#!/usr/bin/env python3
"""
bench-parallel.py — concurrent-request benchmark through llama-swap.

Same method as bench-ctx.py (native /completion via /upstream/<model>, temp 0,
cache_prompt=false, ignore_eos, warmup, 3 iters), but fires N requests CONCURRENTLY
to measure how the server's continuous batching (--parallel / -np) holds up under
real parallel load. Reports per-request pp/tg, aggregate decode tok/s (sum across
requests), wall time, and peak VRAM sampled during the run.

With -np 2 the model's -c is split per slot (e.g. 32768 -> 16384/slot), so each
request's prompt must stay under the per-slot ceiling.

Адрес API и способ снять VRAM берутся из rig.local.env (см. rig.py):
    python3 bench/bench-parallel.py [model_id] [depth_per_req ...]
"""
import json, time, urllib.request, sys, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rig  # noqa: E402  — параметры стенда из rig.local.env

HOST = rig.api_base()
ITERS   = 3
NPRED   = 96
TIMEOUT = 300
CONC    = 2  # concurrent requests

BASE = ("The quick brown fox jumps over the lazy dog and then keeps running "
        "through the quiet forest. ")
TOK_PER_REPEAT = 18.0


def post(path, body):
    req = urllib.request.Request(HOST + path,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def vram():
    return rig.vram_used_mib()


def one(upstream, prompt, out, idx):
    r = post(f"{upstream}/completion",
             {"prompt": prompt, "n_predict": NPRED, "temperature": 0,
              "cache_prompt": False, "ignore_eos": True})
    out[idx] = r["timings"]


def run_concurrent(upstream, prompt):
    out = [None] * CONC
    threads = [threading.Thread(target=one, args=(upstream, prompt, out, i))
               for i in range(CONC)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    wall = time.time() - t0
    return out, wall


def bench(model, depths):
    upstream = f"/upstream/{model}"
    print(f"\n{'='*72}\n### {model}  —  {CONC} concurrent requests\n{'='*72}")
    print(f"{'depth/req':>9} {'prompt_n':>9} {'pp/req':>9} {'tg/req':>9} "
          f"{'tg_aggr':>9} {'wall(s)':>8} {'vram':>7}")
    for d in depths:
        reps = max(1, round(d / TOK_PER_REPEAT))
        prompt = BASE * reps
        # warmup (concurrent, discarded)
        try:
            run_concurrent(upstream, prompt)
        except Exception as e:
            print(f"  warmup {d} failed: {e}")
            continue
        pp_req, tg_req, tg_aggr, walls, pn = [], [], [], [], 0
        peak = 0
        for _ in range(ITERS):
            # sample VRAM in a side thread while the batch runs
            vhold = {"v": 0}
            def sampler():
                for _ in range(6):
                    vhold["v"] = max(vhold["v"], vram())
            st = threading.Thread(target=sampler); st.start()
            out, wall = run_concurrent(upstream, prompt)
            st.join()
            peak = max(peak, vhold["v"])
            walls.append(wall)
            per_pp = [t["prompt_per_second"] for t in out]
            per_tg = [t["predicted_per_second"] for t in out]
            pn = out[0]["prompt_n"]
            pp_req.append(sum(per_pp) / len(per_pp))
            tg_req.append(sum(per_tg) / len(per_tg))
            tg_aggr.append(sum(per_tg))
        appa = sum(pp_req)/len(pp_req)
        atgr = sum(tg_req)/len(tg_req)
        atga = sum(tg_aggr)/len(tg_aggr)
        awall = sum(walls)/len(walls)
        print(f"{d:>9} {pn:>9} {appa:>9.1f} {atgr:>9.1f} {atga:>9.1f} "
              f"{awall:>8.2f} {peak:>7}")


def main():
    args = sys.argv[1:]
    model = args[0] if args and not args[0].isdigit() else "gemma-4-26b-a4b-qat"
    depths = [int(a) for a in args if a.isdigit()] or [8000, 14000]
    bench(model, depths)


if __name__ == "__main__":
    main()
