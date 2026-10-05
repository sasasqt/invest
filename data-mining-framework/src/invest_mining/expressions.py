"""Typed, causal factor expressions.

Expressions are written in a small Python-like language and parsed into an AST::

    cs_rank(-(close / delay(close, 5) - 1))
    ts_corr(returns, volume, 20) * cs_zscore(ts_mean(returns, 10))

Every operator is causal by construction: time-series operators look only backwards
along the date axis of a wide (date x instrument) panel; cross-sectional operators use
only same-date values. Invalid numerical domains (log of non-positive values, division by
~0, constant windows) yield missing values, never infinities. Operator semantics are
versioned by :data:`OPERATOR_VERSION`; change it whenever any result could change.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import pandas as pd

OPERATOR_VERSION = "1"
BASE_FIELDS = ("open", "high", "low", "close", "volume")
# Derived features and the number of extra past sessions each needs.
DERIVED_FIELDS: dict[str, int] = {"returns": 1, "dollar_volume": 0, "intraday_return": 0}
FEATURES = (*BASE_FIELDS, *DERIVED_FIELDS)
_EPS = 1e-12

Panel: TypeAlias = Mapping[str, pd.DataFrame]
Value: TypeAlias = "pd.DataFrame | float"


class ExpressionError(ValueError):
    """Raised for syntactically or semantically invalid expressions."""


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
        if node.id not in FEATURES:
            raise ExpressionError(f"unknown feature {node.id!r}; available: {FEATURES}")
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
# Evaluation


def build_panel(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Long bars -> wide date x instrument frames for base and derived features."""
    panel: dict[str, pd.DataFrame] = {}
    for field in BASE_FIELDS:
        wide = bars.pivot(index="date", columns="instrument", values=field).sort_index()
        panel[field] = wide.astype("float64")
    panel["returns"] = _clean(panel["close"] / panel["close"].shift(1) - 1.0)
    panel["dollar_volume"] = panel["close"] * panel["volume"]
    panel["intraday_return"] = panel["close"] / panel["open"] - 1.0
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
                out = spec.fn(_frame(vals[0], like))
            out = _clean(_frame(out, like))
        cache[key] = out
        return out

    result = go(tree)
    return _frame(result, like).astype("float64")


# ---------------------------------------------------------------------------
# Random generation (search baseline)


TS_OPS = ("delay", "delta", "ts_mean", "ts_sum", "ts_std", "ts_min", "ts_max", "ts_rank")
WINDOWS = (2, 3, 5, 10, 20, 60)


def random_expression(rng: np.random.Generator, max_depth: int = 4) -> Node:
    """Sample a random well-typed expression (uniform over a simple grammar)."""

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

    node = grow(max_depth)
    # Round-trip through text so generated and parsed trees are identical.
    return parse(str(node))
