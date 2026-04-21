"""What sports are in our e22 match sample?"""
import pandas as pd
df = pd.read_parquet("experiments/e22_cross_venue_spread/data/06_drilldown.parquet")
print(f"total: {len(df)}")
# infer sport from sm_event by looking at names
def sport_guess(row):
    s = (row.get("sm_event","") or "").lower()
    q = (row.get("pm_question","") or "").lower()
    text = f"{s} {q}"
    # heuristic
    if any(w in text for w in ["padres","yankees","dodgers","mlb","cubs","sox","braves"]): return "baseball"
    if any(w in text for w in ["nba","lakers","celtics","warriors","suns","spurs"]): return "basketball"
    if any(w in text for w in ["nhl","oilers","islanders","canadiens","rangers","blackhawks"]): return "ice_hockey"
    if any(w in text for w in ["nfl","steelers","eagles","patriots"]): return "american_football"
    if any(w in text for w in ["hsu","cassone","atp","wta"]): return "tennis"
    return "football_soccer"

df["sport"] = df.apply(sport_guess, axis=1)
print("\nsport distribution:")
print(df["sport"].value_counts())
print("\nclean sample 0.55-0.60 bucket details:")
clean = df[df["spread"].abs() <= 0.15].copy()
fav = clean[(clean["pm_yes"]>=0.55) & (clean["pm_yes"]<0.60)]
for _, r in fav.iterrows():
    print(f"  {r['pm_team']:<28}  sport={sport_guess(r)}  pm={r['pm_yes']:.3f} sm={r['sm_mid']:.3f}")
