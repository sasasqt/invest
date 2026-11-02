#### 5. Audit financial and research validity

Use independent reasoning and small hand-calculated examples. Passing the repository's own tests is insufficient.

- **Causality:** future observations and later revisions must not change past features, decisions, eligibility or fills. Respect the repository's label-horizon conventions when perturbing future data; a forward label legitimately depends on observations inside its declared horizon.

- **Point-in-time data:** verify membership, fundamentals availability, revisions, adjustments, as-traded prices and corporate-action assumptions. Check survivorship and missing-history limitations.

- **Execution and accounting:** reconcile holdings, cash, equity, realized/unrealized P&L, long/short signs, fills, partial fills, turnover, commissions, spread, impact, borrow, financing and settlements.

- **Return definitions:** verify gross/net equity, CAGR, annualization, risk-free treatment, drawdown, insolvency, missing-session handling and benchmark alignment.

- **Mining versus portfolios:** distinguish signal diagnostics from executable returns. Check overlapping forward horizons, quantile/tail membership, ties, orientation, sample counts and the treatment of missing outcomes.

- **Inference and selection:** inspect train/development/confirmation boundaries, purging, embargoes, trial counts, failed or repeated proposals, multiple testing, frozen factor selection and evidence propagation.

- **Uncertainty and verdicts:** inspect dependence assumptions, resampling, undefined statistics, null simulations, small samples and unsupported claims of confirmation.

- **Reporting:** verify tables, JSON, Markdown and plotted figures agree. Missing or undefined values must not silently become zero; rejected, exploratory and inconclusive evidence must remain visible.

- **Reproducibility:** distinguish deterministic replay from fresh vendor downloads, which may revise historical data.

Never inspect or consume reserved confirmation data for this audit. Real market/vendor observations dated `2025-01-01` onward are off limits, as are any additional reserved windows. Use synthetic fixtures or explicitly designated, already-inspected exploratory data before the cutoff. Synthetic future-dated fixtures contain no real reserved observations and must be labeled synthetic. The cutoff concerns observations, not code commits or the date on an audit report. Do not mutate committed ledgers, release reservations, reset research history, or obtain new confirmation evidence. Use a temporary synthetic ledger, or an unmodified disposable copy where an authorized historical workflow requires it; a copy never authorizes reading a reserved period.

