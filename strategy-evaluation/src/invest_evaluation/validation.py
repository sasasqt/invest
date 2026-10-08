"""Portfolio verdict from declared rules, reported beside (never merged with) factor evidence.

The factor's confirmation evidence comes from the signals bundle's metadata, written by
whoever produced the signals; evaluation only copies it. The portfolio verdict uses only
this run's saved metrics, statistics and stress scenarios under ``config.validation``.
Neither verdict changes the other: a supported portfolio does not confirm a rejected
factor, and a confirmed factor does not make an untradable portfolio supported.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd

from invest_evaluation.config import ValidationConfig

VERDICT_VERSION = 2
PORTFOLIO_STATUSES = ("supported", "rejected", "inconclusive", "insufficient_data")


def factor_section(signal_metadata: dict[str, Any]) -> dict[str, Any]:
    """The factor's confirmation evidence as published with its signals, or its absence."""
    evidence = signal_metadata.get("factor_evidence")
    if evidence is None:
        return {
            "status": "not_confirmed",
            "factor_id": signal_metadata.get("factor_id"),
            "reason": "the signals carry no factor confirmation evidence",
        }
    return dict(evidence)


def _check(name: str, status: str, value: Any, threshold: Any, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }


def _positive(name: str, metric: dict[str, Any] | None, detail: str) -> dict[str, Any]:
    if metric is None:
        return _check(name, "not_run", None, "> 0", detail)
    value = metric.get("value")
    if value is None:
        return _check(name, "undefined", None, "> 0", f"{detail}: {metric.get('reason')}")
    return _check(name, "pass" if value > 0 else "fail", value, "> 0", detail)


def portfolio_verdict(
    rules: ValidationConfig,
    returns: pd.Series,
    metrics: dict[str, Any],
    statistics: dict[str, Any],
    scenarios: pd.DataFrame | None,
) -> dict[str, Any]:
    """Classify one fixed portfolio as supported, rejected, inconclusive or insufficient_data.

    Solvency and a valid base net Sharpe are mandatory, regardless of optional rules.
    Known insolvency is rejected even when sample size or statistics are insufficient.
    Every check is saved so missing or adverse evidence is visible in reports.
    """
    clean = returns.dropna()
    n = len(clean)
    window = (
        {"start": str(clean.index[0].date()), "end": str(clean.index[-1].date())} if n else None
    )
    performance = metrics.get("performance", {})
    finite = np.isfinite(clean.to_numpy(dtype=float))
    insolvency = performance.get("insolvency") or {}
    insolvent = bool((clean.loc[finite] <= -1).any()) or (
        insolvency.get("status") == "ok" and insolvency.get("value") is not None
    )
    finite_returns = bool(finite.all())
    solvent = not insolvent and n > 0 and finite_returns
    sharpe = performance.get("sharpe") or {}
    sharpe_value = sharpe.get("value")
    valid_sharpe = (
        sharpe.get("status") == "ok"
        and isinstance(sharpe_value, Real)
        and not isinstance(sharpe_value, bool)
        and math.isfinite(sharpe_value)
    )
    checks = [
        _check(
            "solvency",
            "fail" if insolvent else "pass" if solvent else "undefined",
            False if insolvent else True if solvent else None,
            "positive wealth throughout",
            "insolvent wealth path"
            if insolvent
            else "wealth stays positive"
            if solvent
            else "no returns or non-finite net returns",
        ),
        _check(
            "net_sharpe_validity",
            "pass" if valid_sharpe else "undefined",
            sharpe_value if valid_sharpe else None,
            "finite value with status ok",
            "base net Sharpe is valid"
            if valid_sharpe
            else f"base net Sharpe: {sharpe.get('reason') or sharpe.get('status') or 'missing'}",
        ),
        _check(
            "sessions",
            "pass" if n >= rules.min_sessions else "fail",
            n,
            f">= {rules.min_sessions}",
            "daily net returns in the evaluation period",
        ),
    ]
    boot = statistics.get("bootstrap", {})
    ci = boot.get("sharpe_ci") if boot.get("status") == "ok" else None
    if ci is None:
        checks.append(
            _check(
                "net_sharpe_ci",
                "undefined",
                None,
                "excludes 0",
                f"bootstrap: {boot.get('reason') or boot.get('status')}",
            )
        )
    else:
        lo, hi = ci
        status = "pass" if lo > 0 else "fail"
        checks.append(
            _check(
                "net_sharpe_ci",
                status,
                [lo, hi],
                "lower bound > 0",
                f"{boot['level']:.0%} stationary-bootstrap interval of the net excess Sharpe",
            )
        )
    dsr = statistics.get("deflated_sharpe", {})
    if dsr.get("status") == "ok":
        checks.append(
            _check(
                "deflated_sharpe",
                "pass" if dsr["dsr"] >= rules.min_deflated_sharpe else "fail",
                dsr["dsr"],
                f">= {rules.min_deflated_sharpe}",
                f"n_trials = {dsr['n_trials']}",
            )
        )
    else:
        checks.append(
            _check(
                "deflated_sharpe",
                "undefined",
                None,
                f">= {rules.min_deflated_sharpe}",
                str(dsr.get("reason") or dsr.get("status")),
            )
        )
    for name in rules.stress_scenarios:
        detail = f"net Sharpe under scenario {name}"
        if scenarios is None or name not in set(scenarios["scenario"]):
            checks.append(_positive(f"stress:{name}", None, detail))
            continue
        row = scenarios.loc[scenarios["scenario"] == name].iloc[0]
        insolvency = row.get("insolvency")
        if isinstance(insolvency, str) and insolvency:
            # Losing all capital under a stress is a failed check, not a missing value.
            checks.append(
                _check(f"stress:{name}", "fail", None, "> 0", f"{detail}: insolvent {insolvency}")
            )
            continue
        sharpe = row["sharpe"]
        reason = row.get("sharpe_reason")
        metric = {
            "value": None if pd.isna(sharpe) else float(sharpe),
            "reason": reason if isinstance(reason, str) and reason else "undefined",
        }
        checks.append(_positive(f"stress:{name}", metric, detail))
    if rules.benchmark != "none":
        section_name = "benchmark" if rules.benchmark == "universe" else "external_benchmark"
        section = metrics.get(section_name, {})
        # A section with too few aligned returns holds only its "benchmark" status entry.
        ir = section.get("information_ratio", section.get("benchmark"))
        checks.append(
            _positive(
                f"benchmark:{rules.benchmark}",
                ir,
                f"information ratio against the {section_name.replace('_', ' ')}",
            )
        )

    by_name = {c["name"]: c for c in checks}
    if insolvent:
        status = "rejected"
    elif (
        by_name["sessions"]["status"] != "pass" or by_name["net_sharpe_ci"]["status"] == "undefined"
    ):
        status = "insufficient_data"
    elif by_name["net_sharpe_ci"]["value"][1] < 0:
        status = "rejected"
    elif all(c["status"] == "pass" for c in checks):
        status = "supported"
    else:
        status = "inconclusive"
    return {
        "status": status,
        "reasons": [
            f"{c['name']}: {c['status']} ({c['detail']})" for c in checks if c["status"] != "pass"
        ],
        "evaluation_window": window,
        "checks": checks,
        "rules": {
            "min_sessions": rules.min_sessions,
            "min_deflated_sharpe": rules.min_deflated_sharpe,
            "stress_scenarios": list(rules.stress_scenarios),
            "benchmark": rules.benchmark,
        },
    }


def verdicts(
    signal_metadata: dict[str, Any],
    rules: ValidationConfig,
    returns: pd.Series,
    metrics: dict[str, Any],
    statistics: dict[str, Any],
    scenarios: pd.DataFrame | None,
) -> dict[str, Any]:
    return {
        "verdict_version": VERDICT_VERSION,
        "factor": factor_section(signal_metadata),
        "portfolio": portfolio_verdict(rules, returns, metrics, statistics, scenarios),
        "note": "Factor confirmation and portfolio validation are separate verdicts; "
        "neither changes the other.",
    }
