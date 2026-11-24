# Bayesian, inference and Markov methods: where they fit

**Status:** proposal for review. Nothing here is implemented, scheduled in [TODO.md](../TODO.md) or recorded in the idea store. Assessed against `main` at `eb64ad8` on 2026-11-20.

This note answers one question: do Bayesian methods, further statistical inference, Markov (regime) models and Gibbs sampling or Gibbs (Markov) random fields have a place in invest? It maps each family to the component that would own it, what it would add, its cost and its roadmap slot, and ranks five small proposals (B1 to B5).

## Short answer

Yes, in a few places, as numbers reported beside the existing frequentist checks. None should replace the Holm-adjusted one-shot confirmation (`invest_mining/search.py:296`), which stays the gate, just as factor and portfolio verdicts stay side by side and never merge.

- **Fits M3 now, small:** an empirical Bayes correction for the winner's curse of search families (B1, tested below on 12 synthetic searches), Bayes-factor bounds beside p-values (B3), and a regime-switching option in the synthetic market so STATS-01's calibration is also tested under regime shifts (B2).
- **Fits M3 as refinements of planned work:** regime slices for ROBUST-01 (B4), and spread estimates from daily bars for the cost model (B5).
- **Later (M4 or M5):** hidden Markov regime probabilities as fitted features, hierarchical Bayesian shrinkage of a factor library, Gaussian random fields over asset graphs.
- **Not recommended now:** a probabilistic-programming dependency (PyMC, Stan), discrete Ising or Potts fields, and any Bayesian verdict that replaces the confirmation test.

Terms, because several are overloaded. *Bayesian*: unknowns are distributions, and data update a prior. *Empirical Bayes*: the prior is estimated from many similar estimates, here the roughly 130 scored formulas of one search. *Markov*: the next state depends only on the current one. *Gibbs sampling*: a Markov chain Monte Carlo (MCMC) algorithm for computing posteriors. *Gibbs or Markov random field*: a joint distribution over many variables linked by a graph. The last two share a name, not a use.

## What invest already has

No Bayesian estimate, Markov model or graph exists in the three packages. Their runtime dependencies are NumPy, pandas, PyArrow and Matplotlib only, so a method that needs SciPy, statsmodels or scikit-learn adds a dependency. All packages declare Python 3.11 or later.

| Method | Where | Note |
| --- | --- | --- |
| Newey-West (HAC) mean tests | `invest_mining/diagnostics.py:96`, `invest_evaluation/stats.py:46` | Daily rank IC and strategy returns |
| Stationary bootstrap intervals | `invest_evaluation/stats.py:92` | Sharpe and mean, percentile method |
| Probabilistic and deflated Sharpe | `invest_evaluation/stats.py:140`, `:183` | Without a supplied value, DSR takes the trials' Sharpe variance to be the null sampling variance 1/(n-1) (`stats.py:194`) |
| Purged development and confirmation split | `invest_mining/search.py:88` | Label-overlap purge, optional embargo |
| One-shot Holm test of a frozen family | `invest_mining/search.py:296` | Top five by development t-statistic, one-sided; `benjamini_hochberg` (`diagnostics.py:353`) exists but no command calls it |
| Confirmation-use ledger | `invest_mining/ledger.py` | 2010 to 2024 inspected, 2025 onward reserved |
| Rule-based portfolio verdict | `invest_evaluation/validation.py` | Bootstrap interval, DSR, stress scenarios |

Still open: null-simulation calibration (STATS-01), regime, universe and parameter perturbations (ROBUST-01) and learned models (TRAIN-01).

## Bayesian shrinkage and empirical Bayes

### Winner's curse in search families (B1)

`invest-mine search` scores about 130 unique formulas on development data and freezes the top five by HAC t-statistic. Those five were chosen for scoring high, so their development scores overstate their true effect (selection bias, or regression to the mean). Efron (2011) shows that Tweedie's formula corrects this by empirical Bayes, using the spread of all the estimates, and relates it to James-Stein shrinkage. With z the development t-statistics of all scored formulas (before orientation) and f their density:

```math
\hat{\mu}(z) = z + \frac{d}{dz} \log f(z)
```

**Synthetic test (exploratory).** Three planted reversal strengths, four seeds each, `invest-mine search --trials 200 --seed <seed>`; f is a Gaussian kernel density with Silverman's bandwidth; the shrunk t-statistic is converted back to IC with each formula's own standard error. Means over the four seeds; IC is the mean daily rank IC of the five selected formulas:

| Synthetic market | Raw development IC | Empirical Bayes IC | Confirmation IC | Confirmed (of 5) |
| --- | --- | --- | --- | --- |
| No signal (`reversal_strength = 0`) | 0.0145 | 0.0020 | 0.0012 | 0 |
| Weak reversal (0.0004) | 0.0157 | 0.0051 | 0.0074 | 1.25 |
| Default reversal (0.0015) | 0.0440 | 0.0410 | 0.0480 | 5 |

On the null market the raw development IC overstates the confirmation IC about twelvefold, and the shrunk value lands near it; with a strong signal the shrink is small. Holm already confirms nothing on the null market, so the correction changes no verdict. It improves the effect size used to plan a confirmation (its minimum effect and power) and to report what a family is likely worth. Limits: four seeds per row, one bandwidth, correlated trials (formulas share inputs), synthetic data only. A frequentist alternative with valid intervals is Andrews, Kitagawa and McCloskey (2023); it is heavier to implement.

<details>
<summary>Reproduction script (run from a checkout of <code>eb64ad8</code> with <code>uv run python winners_curse.py &lt;out dir&gt;</code>, about 90 seconds)</summary>

It calls the private helper `invest_data.cli._publish` to publish each market, so it is a scratch script, not a supported workflow.

```python
"""Exploratory: winner's curse in invest-mine search families and an empirical-Bayes
(Tweedie) correction. Synthetic markets only; not research evidence."""

import subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from invest_data.sources import SyntheticConfig, synthetic_market
from invest_data import cli as dcli

OUT = Path(sys.argv[1])
rows = []


def tweedie(z_all, z_sel):
    z_all = np.asarray(z_all, float)
    n = len(z_all)
    h = 1.06 * z_all.std(ddof=1) * n ** (-1 / 5)
    d = (np.asarray(z_sel)[:, None] - z_all[None, :]) / h
    k = np.exp(-0.5 * d * d)
    f = k.sum(1)
    fp = (-d / h * k).sum(1)
    return np.asarray(z_sel) + fp / f  # E[mu | z], unit noise variance


for strength in (0.0, 0.0004, 0.0015):
    for seed in (1, 2, 3, 4):
        tag = f"s{strength}_seed{seed}"
        d = OUT / tag
        cfg = SyntheticConfig(seed=seed, reversal_strength=strength)
        bars = synthetic_market(cfg)
        dcli._publish(
            bars,
            d / "data",
            f"syn-{tag}",
            dcli.SYNTHETIC_METADATA,
            {"sources": ["scratch"], "config": cfg.to_dict()},
            "parquet",
        )
        subprocess.run(
            [
                "invest-mine",
                "search",
                "--data",
                str(d / "data"),
                "--trials",
                "200",
                "--seed",
                str(seed),
                "--out",
                str(d / "search"),
            ],
            check=True,
            capture_output=True,
        )
        led = pd.read_csv(d / "search" / "ledger.csv")
        conf = pd.read_csv(d / "search" / "confirmation.csv")
        ev = led[led.status == "evaluated"].copy()
        ev["raw_t"] = ev.orientation * ev.dev_t
        sel = ev[ev.selected].set_index("expression")
        shr_t = tweedie(ev.raw_t, sel.raw_t) * sel.orientation
        se = sel.dev_mean_rank_ic / sel.dev_t
        sel["eb_ic"] = shr_t * se
        conf = conf.set_index("expression")
        sel = sel.join(
            conf[["confirm_mean_rank_ic", "status"]].rename(columns={"status": "cstatus"})
        )
        rows.append(
            {
                "strength": strength,
                "seed": seed,
                "n_eval": len(ev),
                "dev_ic": sel.dev_mean_rank_ic.mean(),
                "eb_ic": sel.eb_ic.mean(),
                "confirm_ic": sel.confirm_mean_rank_ic.mean(),
                "passed": int((sel.cstatus == "confirmation_passed").sum()),
            }
        )
df = pd.DataFrame(rows)
print(df.round(4).to_string(index=False))
print(df.groupby("strength")[["dev_ic", "eb_ic", "confirm_ic", "passed"]].mean().round(4))
```

</details>

### Bayes-factor bounds beside p-values (B3)

Harvey (2017) proposes reporting the minimum Bayes factor (MBF) with each p-value: MBF = exp(-Z²/2) for a test with z-score Z, and the "Bayesianized p-value" MBF × prior odds / (1 + MBF × prior odds), the least probability that the null is true. Example from this repository: the 5-day reversal's full-sample rank IC on Yahoo 2010 to 2024 has HAC t = -2.06 and two-sided p = 0.039 ([run record](../runs/yahoo-test/2026-10-07/mining/diagnostics/metrics.json)). Its MBF is 0.12, so the null keeps at least 11% probability at even prior odds and at least 32% at 4:1 odds against an effect. Cost: one small function in mining and one in evaluation (the components never import each other), with the prior odds declared before results. It informs and never gates.

### Shrinkage for a future factor library and combination

- Jensen, Kelly and Pedersen (2023) fit a Bayesian model of factor replication: most factors replicate, cluster into 13 themes, and their evidence is strengthened by the number of factors. Chen and Zimmermann (2019) find publication-bias-adjusted returns only 12.3% below in-sample returns, because returns vary across predictors more than noise explains. Both fit invest only once it holds a library of confirmed factors (M4 or M5).
- Kozak, Nagel and Santosh (2020) shrink a combination of many factors with an economically motivated prior on low-variance principal components. Ridge regression, the first learned baseline planned for TRAIN-01, is already the posterior mean under a Gaussian prior.
- Avramov and Zhou (2010) review Bayesian portfolio choice under parameter and model uncertainty. That matters once evaluation sizes positions from forecasts; today it ranks names into buckets.

## Frequentist inference gaps

The largest inference gap is not Bayesian: the confirmation gate and the portfolio rules have not been calibrated on repeated null simulations (STATS-01). Every addition in this note should be measured by that harness before it is trusted.

| Method | What it would add | Cost | Slot |
| --- | --- | --- | --- |
| Null and planted-signal calibration | False-confirmation rate and power of the whole pipeline, with Monte Carlo errors | M | M3, STATS-01 |
| Romano-Wolf stepdown (2005) | Family-wise error control that uses the joint dependence of the tests by resampling, so it rejects more false nulls than single-step methods | M | M3, beside a Reality Check or SPA family test |
| Share of null formulas (pi0) | How many of a search's formulas carry no signal: Storey (2002) estimates it from p-values; Barras, Scaillet and Wermers (2010) used it to find 75% of mutual funds have zero alpha | S | M3, report only (part of B1) |
| Anytime-valid test (e-process) | Valid repeated looks at a candidate watched over time | M | After prospective forward tests |

With a family of five, a stepdown method probably gains little over Holm (an inference, not measured); it pays off for large families. The share of null formulas uses development data the search already inspected, so it describes the grammar and the data and never counts as confirmation.

## Hidden Markov and regime-switching models

Regime-switching models belong first in the synthetic market, where they stress the statistics, and only later in mining features. The one trap is look-ahead through smoothed regime probabilities.

A hidden Markov model lets an unobserved state switch by a Markov chain and change the return distribution; Hamilton (1989) gave the filter and maximum-likelihood fit. Ang and Timmermann (2012) review how regimes reproduce fat tails, changing volatility, skewness and time-varying correlations. Factor payoffs depend on state too: Daniel and Moskowitz (2016) find momentum crashes partly forecastable, in "panic" states after market declines with high volatility, and a dynamic version roughly doubles the static strategy's Sharpe ratio.

| Place | Owner | What it adds | Cost | Slot |
| --- | --- | --- | --- | --- |
| Regime switch in the synthetic market (B2) | `invest_data/sources.py` (`SyntheticConfig`) | A two-state chain switching market volatility or the planted reversal strength, off by default with byte-identical output; tests whether HAC lags, the block bootstrap and the gate stay calibrated under abrupt, persistent shifts | S, NumPy only, no fitting | M3, used by STATS-01 |
| Regime slices (B4) | Mining diagnostics, evaluation reports | IC and portfolio results per pre-declared market state; rule-based causal states from trailing market data first, since an HMM adds little for slicing; secondary endpoints per [ALPHA_VALIDATION.md](../data-mining-framework/ALPHA_VALIDATION.md) | S to M | M3, ROBUST-01 |
| Regime probability as a fitted feature | Mining training | Filtered probability of a stressed state as an input or gate for a learned model | M, plus a dependency choice | M4 after TRAIN-01, kept only if it beats the ridge baseline (COMPARE-01) |
| Regime-scaled trading | Mining forecasts, evaluation strategies | Scaling a factor by forecast mean and variance | M | M5; needs POLICY-01 only if it reads holdings |

**Look-ahead.** statsmodels' `MarkovRegression` offers both `filter` (the Hamilton filter) and `smooth`. Smoothed probabilities at date t use data after t, and filtered ones still leak when the parameters were fitted on the whole sample. Fit on development data only, freeze the parameters with a training cutoff, and run the filter forward, the same rule REVIEW-13 enforced for prices.

**Tooling.** The generator needs no estimation. For fitting: statsmodels 0.15.0 (BSD-3; pulls SciPy, patsy and formulaic); hmmlearn 0.3.3 (BSD; pulls scikit-learn and SciPy), whose PyPI description says it is "under limited-maintenance mode"; or a two-state Gaussian filter in NumPy, estimated at about 150 lines.

A plain Markov chain also has a cheap descriptive use: the transition matrix of decile membership between rebalances.

## MCMC and Gibbs sampling

Gibbs sampling computes posteriors; it is not worth adding for its own sake. Its one concrete use in invest today is estimating trading spreads from daily bars, and a closed-form estimator does that more cheaply.

**Spreads from daily bars (B5).** Hasbrouck (2009) proposes a Gibbs estimate of the effective trading cost from daily closing prices; in his validation sample it correlates 0.965 with the transaction-level estimate. Ardia, Guidotti and Kroencke (2024) estimate spreads in closed form from open, high, low and close prices (EDGE); the MIT-licensed `bidask` package (pandas and NumPy only) implements it with rolling and expanding windows. In invest this would replace the single configured half-spread with a trailing per-name estimate known at the decision date, like the existing volatility and ADV windows. Two cautions, both unverified reasoning: total-return adjustment scales a day's four prices by one factor, so within-day ratios survive it; and S&P 100 spreads are very small, so the estimates may not be distinguishable from zero there. The first step is to measure that on a saved snapshot, before any engine change.

**Bayesian regime models.** Albert and Chib (1993) treat hidden regime states as missing data and draw them with the Gibbs sampler, which gives full parameter uncertainty. That is worth it only if regime features are adopted and their parameter uncertainty matters; the maximum-likelihood fit comes first.

**Dependency cost** (PyPI, 2026-11-20):

| Library | Latest | Python | Pulls in | Verdict |
| --- | --- | --- | --- | --- |
| PyMC | 6.4.0 | 3.12 or later | PyTensor, ArviZ | Would drop Python 3.11 support |
| NumPyro | 0.22.0 | 3.11 or later | JAX (Windows wheels exist) | Heavy for the uses found |
| statsmodels | 0.15.0 | 3.10 or later | SciPy, patsy, formulaic | Reasonable if TRAIN-01 adopts SciPy anyway |
| bidask | 2.1.0 | 3.6 or later | pandas, NumPy | Light; the reuse for B5 |

Prefer closed-form and empirical Bayes estimates, write any needed sampler in NumPy, and add no probabilistic-programming library until a model needs one.

## Markov and Gibbs random fields over asset graphs

Random fields over asset graphs are the weakest fit today. They need relations invest does not have (point-in-time sectors, supply chains) or a graph learned from lagged returns, so they belong to M4 or M5.

A Gaussian Markov random field is a multivariate normal with a sparse inverse covariance (precision) matrix; a zero means two assets are independent given all the others. The graphical lasso (Friedman, Hastie and Tibshirani) estimates such a graph with a lasso penalty on the precision matrix. Two uses fit invest:

- **Risk and sizing:** a sparse or shrunk covariance (for example Ledoit and Wolf, 2004) for risk-based weights, once evaluation sizes by covariance.
- **Redundant candidates:** a partial-correlation graph of the candidates' daily IC series, whose clusters would give an effective number of independent trials for the DSR and a sharper redundancy filter than the current rule, which drops a candidate whose mean rank correlation with a chosen one exceeds 0.7 (`invest_mining/search.py:273`).

Signals spread over a graph have some evidence. Cohen and Frazzini (2008) find return predictability across customer-supplier links, which needs link data invest lacks. Pu, Roberts, Dong and Zohren (2023) learn a graph from momentum features of 64 futures and report a network momentum strategy with a Sharpe ratio of 1.5 (self-reported, futures). On Yahoo data the only leakage-safe graph is one learned from trailing returns, and it should beat the same model with the edges removed. For discrete Gibbs fields (Ising or Potts models), no finance evidence worth citing turned up, so they are not recommended.

## Ranked proposals

All five fit inside work the agreed order schedules after the REVIEW-10 checkpoint (STATS-01, ROBUST-01, ROBUST-02), so none jumps the queue.

| Rank | Proposal | Owner | Cost | Slot |
| --- | --- | --- | --- | --- |
| B1 | Empirical Bayes estimate of the selected family's IC, plus the share of null formulas, in the search's `config.json` and report | `invest_mining/search.py`, `reporting.py` | S | M3, beside STATS-01 |
| B2 | Two-state regime switch in the synthetic market, off by default | `invest_data/sources.py` | S | M3, used by STATS-01 |
| B3 | Minimum Bayes factor and Bayesianized p-value beside confirmation and HAC p-values, prior odds declared in advance | mining `confirmation.csv`, evaluation `report.md` | XS to S | M3, REPORT-02 |
| B4 | Regime slices in the robustness matrix, rule-based causal states first | Mining diagnostics, evaluation reports | S to M | M3, ROBUST-01 |
| B5 | Trailing per-name spread estimates (EDGE, with Hasbrouck's Gibbs estimate as a cross-check), measured on a snapshot first | Evaluation cost model | M | M3, ROBUST-02, or with SCOPE-01 data |

## Limits and open questions

The synthetic test is small and exploratory. The papers were read through their abstracts or publisher metadata, except Harvey (2017), whose full text gave the Bayes-factor formulas; claims that rest on reasoning rather than a source are marked where they appear. Open questions for later searches: out-of-sample evidence that regime features improve cross-sectional equity factor timing after 2010; the accuracy of EDGE and the Gibbs estimate for large-cap US stocks with spreads under 5 basis points; finance uses of Ising or Potts models with out-of-sample tests; empirical Bayes corrections for strongly correlated estimates; and graphical lasso on factor IC series for counting effective trials.

## Sources

- Albert, J. H. and Chib, S. (1993). Bayes inference via Gibbs sampling of autoregressive time series subject to Markov mean and variance shifts. *Journal of Business & Economic Statistics* 11(1). [RePEc](https://ideas.repec.org/a/bes/jnlbes/v11y1993i1p1-15.html)
- Andrews, I., Kitagawa, T. and McCloskey, A. (2023). Inference on winners. *Quarterly Journal of Economics* 139(1), 2024 issue. [DOI](https://doi.org/10.1093/qje/qjad043)
- Ang, A. and Timmermann, A. (2012). Regime changes and financial markets. *Annual Review of Financial Economics* 4. [DOI](https://doi.org/10.1146/annurev-financial-110311-101808)
- Ardia, D., Guidotti, E. and Kroencke, T. A. (2024). Efficient estimation of bid-ask spreads from open, high, low, and close prices. *Journal of Financial Economics* 161. [DOI](https://doi.org/10.1016/j.jfineco.2024.103916); [bidask on PyPI](https://pypi.org/project/bidask/)
- Avramov, D. and Zhou, G. (2010). Bayesian portfolio analysis. *Annual Review of Financial Economics* 2. [DOI](https://doi.org/10.1146/annurev-financial-120209-133947)
- Barras, L., Scaillet, O. and Wermers, R. (2010). False discoveries in mutual fund performance: measuring luck in estimated alphas. *Journal of Finance* 65(1). [DOI](https://doi.org/10.1111/j.1540-6261.2009.01527.x)
- Chen, A. Y. and Zimmermann, T. (2019). Publication bias and the cross-section of stock returns. *Review of Asset Pricing Studies* 10(2), 2020 issue. [DOI](https://doi.org/10.1093/rapstu/raz011)
- Cohen, L. and Frazzini, A. (2008). Economic links and predictable returns. *Journal of Finance* 63(4). [DOI](https://doi.org/10.1111/j.1540-6261.2008.01379.x)
- Daniel, K. and Moskowitz, T. J. (2016). Momentum crashes. *Journal of Financial Economics* 122(2). [NBER w20439](https://www.nber.org/papers/w20439)
- Efron, B. (2011). Tweedie's formula and selection bias. *Journal of the American Statistical Association* 106(496). [DOI](https://doi.org/10.1198/jasa.2011.tm11181)
- Friedman, J., Hastie, T. and Tibshirani, R. (2008). Sparse inverse covariance estimation with the graphical lasso. *Biostatistics* 9(3). [DOI](https://doi.org/10.1093/biostatistics/kxm045)
- Hamilton, J. D. (1989). A new approach to the economic analysis of nonstationary time series and the business cycle. *Econometrica* 57(2). [RePEc](https://ideas.repec.org/a/ecm/emetrp/v57y1989i2p357-84.html)
- Harvey, C. R. (2017). Presidential address: the scientific outlook in financial economics. *Journal of Finance* 72(4). [PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P131_The_scientific_outlook.pdf)
- Hasbrouck, J. (2009). Trading costs and returns for U.S. equities: estimating effective costs from daily data. *Journal of Finance* 64(3). [DOI](https://doi.org/10.1111/j.1540-6261.2009.01469.x)
- Jensen, T. I., Kelly, B. and Pedersen, L. H. (2023). Is there a replication crisis in finance? *Journal of Finance* 78(5). [DOI](https://doi.org/10.1111/jofi.13249)
- Kozak, S., Nagel, S. and Santosh, S. (2020). Shrinking the cross-section. *Journal of Financial Economics* 135(2). [NBER w24070](https://www.nber.org/papers/w24070)
- Ledoit, O. and Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *Journal of Multivariate Analysis* 88(2). [DOI](https://doi.org/10.1016/S0047-259X(03)00096-4)
- Pu, X., Roberts, S., Dong, X. and Zohren, S. (2023). Network momentum across asset classes. [arXiv:2308.11294](https://arxiv.org/abs/2308.11294)
- Romano, J. P. and Wolf, M. (2005). Stepwise multiple testing as formalized data snooping. *Econometrica* 73(4). [RePEc](https://ideas.repec.org/a/ecm/emetrp/v73y2005i4p1237-1282.html)
- Storey, J. D. (2002). A direct approach to false discovery rates. *Journal of the Royal Statistical Society B* 64(3). [DOI](https://doi.org/10.1111/1467-9868.00346)
- statsmodels `MarkovRegression` [documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.regime_switching.markov_regression.MarkovRegression.html); PyPI pages of [hmmlearn](https://pypi.org/project/hmmlearn/), [PyMC](https://pypi.org/project/pymc/), [NumPyro](https://pypi.org/project/numpyro/), [statsmodels](https://pypi.org/project/statsmodels/) and [jaxlib](https://pypi.org/project/jaxlib/).
