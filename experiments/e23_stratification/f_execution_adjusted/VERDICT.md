# Agent F — Verdict

**Small live test ($500-$1000 sanity), NOT full deployment, NOT kill.**

The +25.8pp raw edge at the 0.55-0.60 T-7d sports bucket survives all layers
of realistic execution friction — net edge at the expected operating cell
($500 order, 3 bps sports fees, one-sided buy-and-hold fee model) is
**+23.8pp**, and at a ~71% fill probability the expected edge per qualifying
bet is **+16.9pp**. Fees are essentially noise (even V2 15bps worst-case costs
0.37pp); slippage and fill probability are the binding frictions. At $5-10k
capital the conservative div-5 scenario returns $4-8k/yr (77-85%
annualized) — attractive but dominated by edge-survival risk. Deploy the
strategy on MLB / NBA / NFL / NHL only (where liquidity and per-sport
yes-rate both hold up), with a $1,000 position-size cap, no fee-environment
gating needed, and a pre-set kill gate if realized yes_rate in-bucket falls
below 0.72 over a rolling 30-bet window. Do NOT deploy $10k+ until the
e16-prescribed 30-day forward validation returns green — a small $500-$1000
test serves both as live-edge confirmation and as execution-assumption check
without committing the bankroll.
