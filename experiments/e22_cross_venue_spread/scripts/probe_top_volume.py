"""Identify high-volume sports markets on each venue to target for matching."""
import pmxt

VENUES = [
    ("polymarket", pmxt.Polymarket()),
    ("kalshi", pmxt.Kalshi()),
    ("smarkets", pmxt.Smarkets()),
]

for name, client in VENUES:
    print(f"\n=== {name} top 20 by vol24h in sports ===")
    ms = client.fetch_markets()
    # Broad sports filter - include esports for now
    def is_sports_broad(m):
        cat = (m.category or "").lower()
        tags = [t.lower() for t in (m.tags or [])]
        return ("sport" in cat or any("sport" in t for t in tags)
                or cat in ("football", "basketball", "baseball", "ice_hockey",
                           "cricket", "tennis", "american_football",
                           "rugby_union", "soccer", "mma", "ufc"))
    sports = [m for m in ms if is_sports_broad(m) and m.volume_24h is not None]
    sports.sort(key=lambda m: -(m.volume_24h or 0))
    for m in sports[:20]:
        out_str = " / ".join(f"{o.label}={o.price:.3f}" for o in m.outcomes[:3])
        rd = m.resolution_date
        print(f"  vol24h={m.volume_24h:>10.0f}  rdate={rd}  "
              f"title={m.title[:60]!r}  outs=[{out_str}]")
