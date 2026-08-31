#!/usr/bin/env python3
"""Sample Steam concurrent-player counts for one tier and write one CSV per run.

Runs on GitHub Actions (stdlib only, no pip installs). Data source is Steam's
public, keyless APIs. Output: data/<tier>/<YYYY-MM>/<YYYY-MM-DD_HHMM>.csv with
header  ts,appid,concurrent,peak_in_game,src

    collect.py daily --shard 0/2   # half the daily tier (matrix-sharded in CI)
    collect.py sparse    # ~6k  games, ~2.2h  (weekly)
    collect.py top       # top-100 batch, 1 request (manual / smoke test)

## Why this lives in the cloud

The site's builder is on wuko's laptop and cannot move (it reads ~4.8GB of raw
snapshots). But the *collectors* only need network, so they belong somewhere
that does not sleep: the laptop has silently missed sweeps three times
(NTFS mount failure, a suspended window, a job that died without a trace).
Same split as scos-lab/steamcozy-prices: cloud appends CSV increments to git,
the laptop imports them (`pipeline/collect_ccu.py --sync-cloud`).

## Tier lists are shipped in, not computed here

`tiers/daily.json` / `tiers/sparse.json` are produced on the laptop by
`collect_ccu.py --export-tiers` (the assignment needs local state: news db,
price history, steamcharts coverage) and committed here — same role as
`watchlist.json` in the prices repo.

⚠ **They are snapshots and they rot.** A game that goes quiet should drop to
sparse; a game that wakes up should rise to daily. The laptop's daily chain
re-exports and pushes them, so a stale file here means that push stopped —
check `tiers/*.json` mtime in git if the tier sizes look wrong.

## Politeness

1.3s between single-app requests (~0.77 req/s), matching what the laptop used.
GitHub runner IPs are shared, so 429s are retried with backoff rather than
hammered. A partial CSV is still committed (`if: always()` in the workflow) —
losing a run's tail is better than losing the whole run.
"""
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SLEEP = 1.3
BULK_API = ("https://api.steampowered.com/ISteamChartsService/"
            "GetGamesByConcurrentPlayers/v1/")
SINGLE_API = ("https://api.steampowered.com/ISteamUserStats/"
              "GetNumberOfCurrentPlayers/v1/")
UA = {"User-Agent": "steamcozy.com ccu collector (suggest@steamcozy.com)"}


def get(url, tries=4):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            code = getattr(e, "code", None)
            if attempt == tries - 1:
                return None
            time.sleep(10 * (attempt + 1) if code == 429 else 5)
    return None


def out_path(tier: str, shard=None) -> Path:
    now = datetime.now(timezone.utc)
    p = ROOT / "data" / tier / f"{now:%Y-%m}"
    p.mkdir(parents=True, exist_ok=True)
    tag = f"_s{shard[0]}" if shard else ""
    return p / f"{now:%Y-%m-%d_%H%M}{tag}.csv"


def run_top(w) -> int:
    j = get(BULK_API)
    ranks = ((j or {}).get("response") or {}).get("ranks") or []
    ts = int(time.time())
    for e in ranks:
        w.writerow([ts, e["appid"], e.get("concurrent_in_game") or 0,
                    e.get("peak_in_game") or 0, "bulk"])
    return len(ranks)


def run_single(w, appids, fh) -> int:
    """concurrent 留空 = API 拒答 (多为下架), 与 0 (在线零人) 不是一回事。"""
    ok = 0
    for i, a in enumerate(appids):
        j = get(f"{SINGLE_API}?appid={a}", tries=2)
        resp = (j or {}).get("response") or {}
        val = int(resp.get("player_count") or 0) if resp.get("result") == 1 else ""
        w.writerow([int(time.time()), a, val, "", "single"])
        if val != "":
            ok += 1
        if i % 500 == 499:
            fh.flush()          # 中途被杀也留下已采到的部分
            print(f"  {i + 1:,}/{len(appids):,} ok={ok}", flush=True)
        time.sleep(SLEEP)
    return ok


def main() -> None:
    # --shard k/n: run 1/n of the tier list (stride slice appids[k::n]).
    # Why: the daily tier grew past what one 6h GH job can hold (13.9k x 1.3s
    # = 5.0h of sleep alone; 3 runs were killed at timeout 2026-08-27..29,
    # always cutting the SAME ~900 tail games). Sharding across a matrix
    # halves wall clock; stride keeps each shard spread over the whole list
    # so a killed shard tail is not one contiguous popularity band.
    # Filenames get _s<k> so parallel shards never collide (importers glob).
    args = sys.argv[1:]
    shard = None
    if "--shard" in args:
        i = args.index("--shard")
        k, n = map(int, args[i + 1].split("/"))
        if not 0 <= k < n:
            sys.exit(f"bad --shard {args[i + 1]!r} (want k/n with 0<=k<n)")
        shard = (k, n)
        del args[i:i + 2]
    tier = args[0] if args else "top"
    if shard and tier == "top":
        sys.exit("--shard makes no sense for the single-request top tier")
    dst = out_path(tier, shard)
    with dst.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "appid", "concurrent", "peak_in_game", "src"])
        if tier == "top":
            n = run_top(w)
        else:
            tf = ROOT / "tiers" / f"{tier}.json"
            if not tf.exists():
                sys.exit(f"missing {tf} — laptop must export/push tier lists first")
            appids = json.loads(tf.read_text())
            if shard:
                k, n = shard
                appids = appids[k::n]
                tier_label = f"{tier} shard {k}/{n}"
            else:
                tier_label = tier
            print(f"{tier_label}: {len(appids):,} games, "
                  f"~{len(appids) * SLEEP / 3600:.1f}h", flush=True)
            n = run_single(w, appids, fh)
    print(f"wrote {dst.relative_to(ROOT)} ({n:,} usable)")


if __name__ == "__main__":
    main()
