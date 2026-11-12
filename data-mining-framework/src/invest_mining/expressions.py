"""Typed, causal factor expressions.

Expressions are written in a small Python-like language and parsed into an AST::

    cs_rank(-(close / delay(close, 5) - 1))
    ts_corr(returns, volume, 20) * cs_zscore(ts_mean(returns, 10))

Every operator is causal by construction: time-series operators look only backwards
along the date axis of a wide (date x instrument) panel; cross-sectional operators use
only same-date values. Invalid numerical domains (log of non-positive values, division by
~0, constant windows) yield missing values, never infinities. Operator semantics are
versioned by :data:`OPERATOR_VERSION`; change it whenever any result could change.

Adjusted bars are not causal by themselves: a later split or dividend rescales an
instrument's whole earlier adjusted history. :func:`check_scale_free` tells which formulas
that constant cancels in; the mining commands refuse the others (BH-2026-11-10-1).
"""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from fractions import Fraction
from typing import TypeAlias

import numpy as np
import pandas as pd

from invest_data.pit import fundamentals_asof, membership_panel

OPERATOR_VERSION = "1"
BASE_FIELDS = ("open", "high", "low", "close", "volume")
# Derived features and the number of extra past sessions each needs.
DERIVED_FIELDS: dict[str, int] = {"returns": 1, "dollar_volume": 0, "intraday_return": 0}
FEATURES = (*BASE_FIELDS, *DERIVED_FIELDS)
# Optional bar columns a formula may read when the bundle has them; never drawn by search.
AS_TRADED_FEATURES = ("close_as_traded",)
# How a feature scales when a later split or dividend rescales one instrument's adjusted
# history by c: prices by c and volume by 1/c (DATA_CONTRACT: volume is adjusted inversely).
# Every other feature (returns, intraday_return, dollar_volume, fund_*, close_as_traded) and
# every constant is unchanged by it.
SCALE_EXPONENTS: dict[str, int] = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": -1}
# Point-in-time fundamentals are exposed as ``fund_<field>`` (see build_panel).
FUNDAMENTAL_FEATURE = re.compile(r"fund_[a-z][a-z0-9_]*")
UNIVERSE_KEY = "universe"  # optional boolean panel entry restricting cross-sections
_EPS = 1e-12

Panel: TypeAlias = Mapping[str, pd.DataFrame]
Value: TypeAlias = "pd.DataFrame | float"


class ExpressionError(ValueError):
    """Raised for syntactically or semantically invalid expressions."""


class ScaleError(ExpressionError):
    """Raised by :func:`check_scale_free` for a formula a later split or dividend can change."""


# ---------------------------------------------------------------------------
# AST


@dataclass(frozen=True)
class Feature:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Const:
    value: float

    def __str__(self) -> str:
        return repr(float(self.value))


@dataclass(frozen=True)
class Call:
    op: str
    args: tuple[Node, ...]
    window: int | None = None

    def __str__(self) -> str:
        if self.op in _INFIX:
            return f"({self.args[0]} {_INFIX[self.op]} {self.args[1]})"
        parts = [str(a) for a in self.args]
        if self.window is not None:
            parts.append(str(self.window))
        return f"{self.op}({', '.join(parts)})"


Node = Feature | Const | Call


@dataclass(frozen=True)
class OpSpec:
    kind: str  # unary | binary | ts | ts2 | cs
    fn: Callable[..., pd.DataFrame]


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace([np.inf, -np.inf], np.nan)


def _frame(x: Value, like: pd.DataFrame) -> pd.DataFrame:
    if isinstance(x, pd.DataFrame):
        return x
    return pd.DataFrame(float(x), index=like.index, columns=like.columns)


def _div(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return _clean(a / b.where(b.abs() > _EPS))


def _log(x: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(np.log(x.where(x > 0)), index=x.index, columns=x.columns)


def _ts_std(x: pd.DataFrame, w: int) -> pd.DataFrame:
    s = x.rolling(w, min_periods=w).std(ddof=1)
    return s.where(s > _EPS)


def _ts_rank(x: pd.DataFrame, w: int) -> pd.DataFrame:
    return x.rolling(w, min_periods=w).rank(pct=True)


def _ts_corr(x: pd.DataFrame, y: pd.DataFrame, w: int) -> pd.DataFrame:
    sx, sy = _ts_std(x, w), _ts_std(y, w)
    c = x.rolling(w, min_periods=w).cov(y, ddof=1)
    return _clean(c / (sx * sy)).clip(-1.0, 1.0)


def _cs_zscore(x: pd.DataFrame) -> pd.DataFrame:
    sd = x.std(axis=1, ddof=1)
    return x.sub(x.mean(axis=1), axis=0).div(sd.where(sd > _EPS), axis=0)


OPS: dict[str, OpSpec] = {
    "neg": OpSpec("unary", lambda x: -x),
    "abs": OpSpec("unary", lambda x: x.abs()),
    "log": OpSpec("unary", _log),
    "sign": OpSpec("unary", lambda x: pd.DataFrame(np.sign(x), index=x.index, columns=x.columns)),
    "add": OpSpec("binary", lambda a, b: a + b),
    "sub": OpSpec("binary", lambda a, b: a - b),
    "mul": OpSpec("binary", lambda a, b: a * b),
    "div": OpSpec("binary", _div),
    "delay": OpSpec("ts", lambda x, w: x.shift(w)),
    "delta": OpSpec("ts", lambda x, w: x - x.shift(w)),
    "ts_mean": OpSpec("ts", lambda x, w: x.rolling(w, min_periods=w).mean()),
    "ts_sum": OpSpec("ts", lambda x, w: x.rolling(w, min_periods=w).sum()),
    "ts_std": OpSpec("ts", _ts_std),
    "ts_min": OpSpec("ts", lambda x, w: x.rolling(w, min_periods=w).min()),
    "ts_max": OpSpec("ts", lambda x, w: x.rolling(w, min_periods=w).max()),
    "ts_rank": OpSpec("ts", _ts_rank),
    "ts_corr": OpSpec("ts2", _ts_corr),
    "cs_rank": OpSpec("cs", lambda x: x.rank(axis=1, pct=True)),
    "cs_zscore": OpSpec("cs", _cs_zscore),
    "cs_demean": OpSpec("cs", lambda x: x.sub(x.mean(axis=1), axis=0)),
}
_INFIX = {"add": "+", "sub": "-", "mul": "*", "div": "/"}
_BINOPS = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div"}
MAX_WINDOW = 252


# ---------------------------------------------------------------------------
# Parsing


def parse(text: str) -> Node:
    """Parse an expression string. Only whitelisted names and operators are accepted."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"syntax error: {exc.msg}") from exc
    node = _convert(tree.body)
    if isinstance(node, Const):
        raise ExpressionError("expression must depend on at least one feature")
    return node


def _window(node: ast.expr, op: str) -> int:
    if not (isinstance(node, ast.Constant) and type(node.value) is int):
        raise ExpressionError(f"{op}: window must be an integer literal")
    w = int(node.value)
    if not 1 <= w <= MAX_WINDOW:
        raise ExpressionError(f"{op}: window {w} outside [1, {MAX_WINDOW}]")
    if op not in ("delay", "delta") and w < 2:
        raise ExpressionError(f"{op}: window must be >= 2")
    return w


def _convert(node: ast.expr) -> Node:
    if isinstance(node, ast.Name):
        known = (*FEATURES, *AS_TRADED_FEATURES)
        if node.id not in known and not FUNDAMENTAL_FEATURE.fullmatch(node.id):
            raise ExpressionError(
                f"unknown feature {node.id!r}; available: {known} or fund_<field>"
            )
        return Feature(node.id)
    if isinstance(node, ast.Constant):
        value = node.value
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ExpressionError(f"unsupported constant {value!r}")
        if not math.isfinite(value):
            raise ExpressionError(f"unsupported constant {value!r}")
        return Const(float(value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _convert(node.operand)
        return Const(-inner.value) if isinstance(inner, Const) else Call("neg", (inner,))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _convert(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        a, b = _convert(node.left), _convert(node.right)
        if isinstance(a, Const) and isinstance(b, Const):
            raise ExpressionError("constant-only sub-expressions are not allowed")
        return Call(_BINOPS[type(node.op)], (a, b))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        op = node.func.id
        spec = OPS.get(op)
        if spec is None:
            raise ExpressionError(f"unknown operator {op!r}")
        args = node.args
        arity = {"unary": 1, "binary": 2, "ts": 2, "ts2": 3, "cs": 1}[spec.kind]
        if len(args) != arity:
            raise ExpressionError(f"{op} expects {arity} arguments, got {len(args)}")
        if spec.kind in ("ts", "ts2"):
            children = tuple(_series_arg(a, op) for a in args[:-1])
            return Call(op, children, _window(args[-1], op))
        if spec.kind == "binary":
            a, b = _convert(args[0]), _convert(args[1])
            if isinstance(a, Const) and isinstance(b, Const):
                raise ExpressionError("constant-only sub-expressions are not allowed")
            return Call(op, (a, b))
        return Call(op, (_series_arg(args[0], op),))
    raise ExpressionError(f"unsupported syntax: {ast.dump(node)[:80]}")


def _series_arg(node: ast.expr, op: str) -> Node:
    child = _convert(node)
    if isinstance(child, Const):
        raise ExpressionError(f"{op}: argument must depend on a feature")
    return child


# ---------------------------------------------------------------------------
# Static properties


def lookback(node: Node) -> int:
    """Number of *past* sessions (beyond the current one) the expression needs."""
    if isinstance(node, Feature):
        return DERIVED_FIELDS.get(node.name, 0)
    if isinstance(node, Const):
        return 0
    child = max(lookback(a) for a in node.args)
    if node.window is None:
        return child
    if node.op in ("delay", "delta"):
        return child + node.window
    return child + node.window - 1


def size(node: Node) -> int:
    if isinstance(node, Call):
        return 1 + sum(size(a) for a in node.args)
    return 1


def depth(node: Node) -> int:
    if isinstance(node, Call):
        return 1 + max(depth(a) for a in node.args)
    return 1


def features_used(node: Node) -> set[str]:
    if isinstance(node, Feature):
        return {node.name}
    if isinstance(node, Call):
        return set().union(*(features_used(a) for a in node.args))
    return set()


def canonical(node: Node | str) -> str:
    """Stable textual form, used for de-duplication and artifact identity."""
    return str(parse(node) if isinstance(node, str) else node)


# ---------------------------------------------------------------------------
# Scale check: is the formula causal on backward-adjusted bars?
#
# A split or dividend after date T multiplies one instrument's open, high, low and close
# before T by a constant c and its volume by 1/c. A value that is homogeneous of degree 0 in
# c depends only on the corporate actions between its inputs' dates and its own date, which
# are known then; any other value ranks or scores names by actions they have not made yet.
# Each node gets a scale: ("pow", e), the value is multiplied by c**e, or ("log", k), the
# value is shifted by k * log(c) (the log of a level). The formula must end at ("pow", 0).

_Scale = tuple[str, Fraction]
_FREE: _Scale = ("pow", Fraction(0))
_PRICES = frozenset(f for f, e in SCALE_EXPONENTS.items() if e > 0)
_CHANGE_OPS = frozenset({"sub", "delta", "ts_std"})
_RESETS = frozenset({"sign", "ts_rank", "ts_corr"})  # results of scale 0 for any argument


def check_scale_free(node: Node) -> None:
    """Raise :class:`ScaleError` unless a later split or dividend leaves the value unchanged.

    The rule (the user's decision of 2026-11-11, BH-2026-11-10-1): prices scale with c and
    volume with 1/c; ``mul`` adds exponents, ``div`` subtracts them, ``add`` and ``sub`` need
    equal ones; ``sign``, ``ts_rank`` and ``ts_corr`` remove the scale; the other operators
    keep it; cross-sectional operators and the formula's value need exponent 0. ``log`` of a
    level is allowed only where its constant cancels (a difference of logs with the same
    exponent, ``delta``, ``ts_std``, ``ts_rank``, ``ts_corr``). Log levels are tracked by their
    exact offset k (the value moves by k * log c): sums add k, ``ts_sum`` multiplies it by the
    window, a constant factor scales it, and only k == 0 counts as cancelled, so
    ``log(close) + log(open)`` stays refused. ``close_as_traded`` does not
    scale, but no time-series operator may read it: as-traded prices jump at each split or
    dividend. The message names the offending part and the form to use instead.
    """
    for sub in _calls(node):
        if OPS[sub.op].kind in ("ts", "ts2"):
            read = set().union(*(features_used(a) for a in sub.args)) & set(AS_TRADED_FEATURES)
            if read:
                raise _as_traded_series_error(sub, sorted(read)[0])
    if _scale(node) != _FREE:
        raise _level_error(node, "as the formula's value")


def _calls(node: Node, *, through_resets: bool = True) -> list[Call]:
    """Calls in ``node``, outermost first (iterative: long formulas need no deep stack).
    With ``through_resets=False``, stop at operators whose result has scale 0 for any
    argument (cross-sectional operators, ``sign``, ``ts_rank``, ``ts_corr``)."""
    found: list[Call] = []
    stack: list[Node] = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, Call):
            continue
        if not through_resets and (current.op in _RESETS or OPS[current.op].kind == "cs"):
            continue
        found.append(current)
        stack.extend(reversed(current.args))
    return found


def _scale(node: Node) -> _Scale:
    if isinstance(node, Feature):
        return ("pow", Fraction(SCALE_EXPONENTS.get(node.name, 0)))
    if isinstance(node, Const):
        return _FREE
    op, args = node.op, node.args
    scales = [_scale(a) for a in args]
    kind, k = scales[0]
    if op in ("ts_rank", "ts_corr"):
        return _FREE  # ranks and correlations ignore a positive factor and a shift
    if OPS[op].kind == "cs":
        if scales[0] != _FREE:
            raise _level_error(args[0], f"under {op}")
        return _FREE
    if op in ("add", "sub"):
        return _sum(node, scales[0], scales[1])
    if op in ("mul", "div"):
        return _product(node, scales[0], scales[1])
    if kind == "log":
        if op == "neg":
            return ("log", -k)
        if op in ("delta", "ts_std"):
            return _FREE  # the constant shift cancels
        if op in ("delay", "ts_mean", "ts_min", "ts_max"):
            return ("log", k)
        if op == "ts_sum" and node.window is not None:
            return ("log", k * node.window)
        raise _log_error(node)
    if op == "sign":
        return _FREE
    if op == "log":
        return _FREE if k == 0 else ("log", k)
    return ("pow", k)  # neg, abs and the remaining time-series operators keep the scale


def _sum(node: Call, a: _Scale, b: _Scale) -> _Scale:
    sign = 1 if node.op == "add" else -1
    if a[0] == "pow" and b[0] == "pow" and a[1] == b[1]:
        return a
    if a[0] == "log" or b[0] == "log":
        ka = a[1] if a[0] == "log" else None
        kb = b[1] if b[0] == "log" else None
        if (ka is None and a != _FREE) or (kb is None and b != _FREE):
            raise _mixed_error(node)
        k = (ka or 0) + sign * (kb or 0)
        return _FREE if k == 0 else ("log", Fraction(k))
    raise _mixed_error(node)


def _product(node: Call, a: _Scale, b: _Scale) -> _Scale:
    if a[0] == "pow" and b[0] == "pow":
        return ("pow", a[1] + b[1] if node.op == "mul" else a[1] - b[1])
    left, right = node.args
    if a[0] == "log" and isinstance(right, Const):
        if right.value == 0:
            return _FREE  # a constant 0 (mul) or missing everywhere (div)
        factor = Fraction(right.value)
        return ("log", a[1] * factor if node.op == "mul" else a[1] / factor)
    if b[0] == "log" and isinstance(left, Const) and node.op == "mul":
        return _FREE if left.value == 0 else ("log", b[1] * Fraction(left.value))
    raise _log_error(node)


def _scaled_features(node: Node) -> set[str]:
    """Features whose scale can reach this node: a cross-sectional operator, ``sign``,
    ``ts_rank`` or ``ts_corr`` removes its argument's scale, so features under one do not
    choose the message."""
    if isinstance(node, Feature):
        return {node.name}
    if isinstance(node, Call) and node.op not in _RESETS and OPS[node.op].kind != "cs":
        return set().union(*(_scaled_features(a) for a in node.args))
    return set()


def _fundamental_over_price(sub: Node) -> str | None:
    """The as-traded form of a fundamental multiplied by or divided by an adjusted price
    whose scale reaches ``sub`` (``fund_eps / close_as_traded``), or None."""
    for call in _calls(sub, through_resets=False):
        if call.op in ("mul", "div"):
            left, right = (_scaled_features(a) for a in call.args)
            for in_denominator, (one, other) in enumerate(((left, right), (right, left))):
                funds = sorted(f for f in one if FUNDAMENTAL_FEATURE.fullmatch(f))
                if funds and other & _PRICES:
                    if call.op == "div" and in_denominator:
                        return f"close_as_traded / {funds[0]}"
                    return f"{funds[0]} {_INFIX[call.op]} close_as_traded"
    return None


# True while a suggested form is checked: messages built for it suggest nothing themselves.
_SUGGESTING: ContextVar[bool] = ContextVar("_SUGGESTING", default=False)


def _suggestion_passes(candidate: Node) -> bool:
    """Whether a form a message would suggest parses as written and passes the check.
    While it runs, messages built for the candidate skip their own suggestions, so two
    suggestions that swap ``close`` and ``close_as_traded`` cannot call each other forever."""
    if _SUGGESTING.get():
        return False
    token = _SUGGESTING.set(True)
    try:
        check_scale_free(parse(str(candidate)))
    except ExpressionError:  # includes ScaleError
        return False
    finally:
        _SUGGESTING.reset(token)
    return True


def _with_as_traded_close(node: Node) -> str | None:
    """``node`` with ``close`` read as traded, when the check passes that form (so no
    time-series operator reads it), else None."""
    if "close" not in features_used(node):
        return None
    candidate = _replace_feature(node, "close", "close_as_traded")
    return str(candidate) if _suggestion_passes(candidate) else None


def _level_error(sub: Node, where: str) -> ScaleError:
    """The decided safe form for a sub-expression that keeps a scale (case by its inputs)."""
    used = _scaled_features(sub)
    as_traded = bool(used & set(AS_TRADED_FEATURES))
    prices, volume = bool(used & _PRICES), "volume" in used
    fund = _fundamental_over_price(sub)
    if fund:
        fund = _with_as_traded_close(sub) or fund
    kind = _scale_or_none(sub)
    why = "a later split or dividend rescales it, so earlier values would change"
    if as_traded and (prices or volume):
        return ScaleError(
            f"{sub} {where} keeps the adjustment factor close / close_as_traded, which reveals "
            "each later split or dividend, so earlier values would change; the factor itself "
            "has no safe form. Use close_as_traded alone for the as-traded price, "
            "dollar_volume for the traded value or volume * close / close_as_traded for "
            "shares traded (not under a time-series operator)"
        )
    if fund:
        return ScaleError(
            f"{sub} {where} combines a per-share fundamental with an adjusted price: {why}. "
            f"Use the as-traded price, as in {fund} (per-share fields as reported at the time; "
            "not "
            "under a time-series operator), or, without that column, a ratio field on its own"
        )
    if kind == "log":
        return ScaleError(
            f"{sub} {where} is the log of an adjusted level: a later split or dividend shifts "
            "it by a constant per instrument, which is not cancelled here, so earlier values "
            "would change. Use log(close_as_traded) for the price (not under a time-series "
            "operator) or log(dollar_volume) for size, or a log difference such as "
            "delta(log(close), 5)"
        )
    if volume and not prices:
        return ScaleError(
            f"{sub} {where} is an adjusted volume level (volume is adjusted inversely to "
            f"prices): {why}. Use shares traded, volume * close / close_as_traded (not under a "
            "time-series operator), log(dollar_volume), or a ratio such as "
            "volume / ts_mean(volume, 20)"
        )
    if prices and any(
        c.op in _CHANGE_OPS and _scale_or_none(c) == "pow-nonzero"
        for c in _calls(sub, through_resets=False)
    ):
        return ScaleError(
            f"{sub} {where} is a price change or spread in adjusted units: {why}. Divide by "
            "the price, as in delta(close, 5) / close, or use a log difference, as in "
            "delta(log(close), 5)"
        )
    return ScaleError(
        f"{sub} {where} is an adjusted price level: {why}. Use close_as_traded (the as-traded "
        "open is open * close_as_traded / close, likewise high and low; not under a "
        "time-series operator) or, without that column, a ratio such as "
        "close / ts_max(close, 252)"
    )


def _scale_or_none(node: Node) -> str | None:
    """'log', 'pow-nonzero', 'free', or None when the node itself is refused."""
    try:
        kind, k = _scale(node)
    except ScaleError:
        return None
    if kind == "log":
        return "log"
    return "free" if k == 0 else "pow-nonzero"


def _mixed_error(node: Call) -> ScaleError:
    a, b = node.args
    fund = _fundamental_over_price(node)
    if fund:
        fund = _with_as_traded_close(node) or fund
        hint = (
            f"for a per-share fundamental use the as-traded price, as in {fund} (not under a "
            "time-series operator)"
        )
    elif _scaled_features(node) & _PRICES:
        hint = (
            "a ratio such as close / delay(close, 5) - 1 or, for a price threshold, the "
            "as-traded price, as in sign(close_as_traded - 5) (not under a time-series operator)"
        )
    else:
        hint = "a ratio such as volume / ts_mean(volume, 20)"
    return ScaleError(
        f"{node} adds or subtracts values that scale differently with a later split or "
        f"dividend ({a} and {b}), so earlier values would change. Make each side scale-free "
        f"first: {hint}"
    )


def _as_traded_series_error(sub: Call, feature: str) -> ScaleError:
    alternative = "Use an adjusted ratio or log difference"
    # Swap in the adjusted close only where nothing else reads an adjusted field:
    # ts_corr(close_as_traded, close) or close_as_traded / close would become constant.
    if not features_used(sub) & set(SCALE_EXPONENTS):
        same_on_adjusted = _replace_feature(sub, feature, "close")
        if _suggestion_passes(same_on_adjusted):
            alternative = (
                f"Use the adjusted close instead, {same_on_adjusted}, or a ratio or log difference"
            )
    return ScaleError(
        f"{sub} applies {sub.op} to {feature}: as-traded prices jump at each split or "
        "dividend, so a time-series operator reads the corporate action as a price move. "
        f"{alternative}, such as close / delay(close, 5) - 1 or delta(log(close), 5)"
    )


def _replace_feature(node: Node, old: str, new: str) -> Node:
    if isinstance(node, Feature):
        return Feature(new) if node.name == old else node
    if isinstance(node, Call):
        return Call(node.op, tuple(_replace_feature(a, old, new) for a in node.args), node.window)
    return node


def _log_error(node: Node) -> ScaleError:
    return ScaleError(
        f"{node} uses the log of an adjusted level where its constant does not cancel: a later "
        "split or dividend shifts that log by a constant per instrument, so earlier values "
        "would change. Use a log difference such as delta(log(close), 5), or "
        "log(close_as_traded)"
    )


# ---------------------------------------------------------------------------
# Evaluation


def build_panel(
    bars: pd.DataFrame,
    *,
    universe: pd.DataFrame | None = None,
    fundamentals: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Long bars -> wide date x instrument frames for base and derived features.

    Bars with a ``close_as_traded`` column add it as a feature of that name.
    ``universe`` (a membership table) adds a boolean ``universe`` entry: cross-sectional
    operators then rank/normalise only across members, while time-series operators still
    use each instrument's full history. ``fundamentals`` adds one ``fund_<field>`` frame per
    field with the value known as of each date's close.
    """
    panel: dict[str, pd.DataFrame] = {}
    for field in BASE_FIELDS:
        wide = bars.pivot(index="date", columns="instrument", values=field).sort_index()
        panel[field] = wide.astype("float64")
    panel["returns"] = _clean(panel["close"] / panel["close"].shift(1) - 1.0)
    panel["dollar_volume"] = panel["close"] * panel["volume"]
    panel["intraday_return"] = panel["close"] / panel["open"] - 1.0
    for field in AS_TRADED_FEATURES:
        if field in bars.columns:
            wide = bars.pivot(index="date", columns="instrument", values=field)
            panel[field] = wide.reindex_like(panel["close"]).astype("float64")
    dates = pd.DatetimeIndex(panel["close"].index)
    instruments = panel["close"].columns
    if universe is not None:
        panel[UNIVERSE_KEY] = membership_panel(universe, dates, instruments)
    if fundamentals is not None:
        for field in sorted(fundamentals["field"].unique()):
            panel[f"fund_{field}"] = fundamentals_asof(fundamentals, field, dates, instruments)
    return panel


def evaluate(node: Node | str, panel: Panel) -> pd.DataFrame:
    """Evaluate an expression on a wide panel; returns a date x instrument frame."""
    tree = parse(node) if isinstance(node, str) else node
    like = panel["close"]
    cache: dict[str, Value] = {}

    def go(n: Node) -> Value:
        key = str(n)
        if key in cache:
            return cache[key]
        out: Value
        if isinstance(n, Feature):
            if n.name not in panel:
                raise ExpressionError(f"feature {n.name!r} is not in the panel")
            out = panel[n.name]
        elif isinstance(n, Const):
            out = n.value
        else:
            spec = OPS[n.op]
            vals = [go(a) for a in n.args]
            if spec.kind == "binary":
                a, b = vals
                out = spec.fn(_frame(a, like), _frame(b, like))
            elif spec.kind in ("ts", "ts2"):
                out = spec.fn(*[_frame(v, like) for v in vals], n.window)
            else:
                arg = _frame(vals[0], like)
                if UNIVERSE_KEY in panel:
                    arg = arg.where(panel[UNIVERSE_KEY])
                out = spec.fn(arg)
            out = _clean(_frame(out, like))
        cache[key] = out
        return out

    result = go(tree)
    return _frame(result, like).astype("float64")


# ---------------------------------------------------------------------------
# Random generation (search baseline)


TS_OPS = ("delay", "delta", "ts_mean", "ts_sum", "ts_std", "ts_min", "ts_max", "ts_rank")
WINDOWS = (2, 3, 5, 10, 20, 60)


_MAX_DRAWS = 1000


def random_expression(rng: np.random.Generator, max_depth: int = 4) -> Node:
    """Sample a random well-typed, scale-free expression (uniform over a simple grammar).

    A draw that :func:`check_scale_free` refuses is drawn again, so search never proposes a
    formula whose price or volume levels a later split or dividend could change. The check
    reads no data; rounding residue on constant windows is not covered (REVIEW-47, REVIEW-48).
    """

    def grow(d: int) -> Node:
        if d <= 1 or rng.random() < 0.25:
            return Feature(str(rng.choice(FEATURES)))
        kind = rng.choice(["unary", "binary", "ts", "ts", "ts2", "cs"])
        if kind == "unary":
            return Call(str(rng.choice(["neg", "abs", "log", "sign"])), (grow(d - 1),))
        if kind == "binary":
            b: Node = Const(float(rng.choice([0.5, 2.0]))) if rng.random() < 0.1 else grow(d - 1)
            return Call(str(rng.choice(list(_INFIX))), (grow(d - 1), b))
        if kind == "ts":
            return Call(str(rng.choice(TS_OPS)), (grow(d - 1),), int(rng.choice(WINDOWS)))
        if kind == "ts2":
            return Call("ts_corr", (grow(d - 1), grow(d - 1)), int(rng.choice(WINDOWS[2:])))
        return Call(str(rng.choice(["cs_rank", "cs_zscore", "cs_demean"])), (grow(d - 1),))

    for _ in range(_MAX_DRAWS):
        # Round-trip through text so generated and parsed trees are identical.
        node = parse(str(grow(max_depth)))
        try:
            check_scale_free(node)
        except ScaleError:
            continue
        return node
    raise ExpressionError(f"no scale-free expression in {_MAX_DRAWS} draws")  # pragma: no cover


def restrict(values: pd.DataFrame, panel: Panel) -> pd.DataFrame:
    """Mask values for instruments not trading (no bar) or outside the universe."""
    values = values.where(panel["close"].notna())
    if UNIVERSE_KEY in panel:
        values = values.where(panel[UNIVERSE_KEY])
    return values
