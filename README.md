# steamcozy-ccu

Concurrent-player samples for [steamcozy.com](https://steamcozy.com), collected
from Steam's public keyless APIs on a schedule. **The git history is the data
history** — every run appends one CSV, nothing is ever rewritten.

Sister repo to [steamcozy-prices](https://github.com/scos-lab/steamcozy-prices),
same shape and same reason for existing.

## Why a repo instead of a server

steamcozy.com is a static site built on a laptop that reads ~4.8 GB of local
snapshots, so the *builder* can't move. The *collectors* only need network, and
a laptop sleeps — this one silently missed sweeps three times (a failed disk
mount, a suspended window, a job that died without a trace). Collection lives
here; the laptop pulls the CSVs back in and bakes them into the site.

## Layout

```
collect.py            stdlib-only collector (no pip install step)
tiers/daily.json      ~9k games sampled once a day   ← generated on the laptop
tiers/sparse.json     ~7k games sampled once a week   ← generated on the laptop
data/<tier>/<YYYY-MM>/<YYYY-MM-DD_HHMM>.csv
                      ts,appid,concurrent,peak_in_game,src
```

`concurrent` empty = the API declined to answer for that appid (usually
delisted). That is **not** the same as `0` (nobody playing), so it is recorded
as empty rather than zero.

## Schedule

The daily sweep's **start hour rotates** across six base hours
(00/04/08/12/16/20 UTC, ~5–6 days each per month). Sampling a game at a fixed
hour every day would produce a "monthly average" that is really *the average of
that one hour* — player counts swing 2–3× within a day, so those are different
statistics. Rotation plus the sweep's own ~3.5 h span covers all 24 hours over a
month, at no extra request cost. GitHub's cron jitter only helps here.

Sparse tier runs Thursdays 02:07 UTC.

## Rate limiting

1.3 s between single-app requests (~0.77 req/s). Runner IPs are shared, so 429s
back off rather than retry hot. Partial output is committed on failure — losing
the tail of a run beats losing the run.

## Data source

`ISteamUserStats/GetNumberOfCurrentPlayers` and
`ISteamChartsService/GetGamesByConcurrentPlayers`, both public and keyless.
No credentials are used or needed. Not affiliated with Valve.

## License

Code MIT. The samples are factual observations of a public API and are offered
freely; attribution to steamcozy.com is appreciated but not required.
