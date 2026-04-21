import pandas as pd
df = pd.read_parquet('experiments/e22_cross_venue_spread/data/03_live_spreads.parquet')
print('columns:', list(df.columns))
print('\nrows:', len(df))
for i, row in df.head(10).iterrows():
    print(f'=== row {i} ===')
    print(f'  pm: {row["pm_title"][:70]}')
    print(f'  pm_team_a={row["pm_team_a"]} yes_a={row["pm_yes_a"]}')
    print(f'  sm_title: {row.get("sm_title", None)}')
    print(f'  sm_outcomes: {row.get("sm_outcomes", None)}')
    print(f'  sm_price_a: {row.get("sm_price_a", None)}')
    print()
