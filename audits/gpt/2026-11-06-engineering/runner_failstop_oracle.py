#!/usr/bin/env python3
"""Static oracle for the audit runner's installed-graph fail-stop invariant.

This checker parses source without importing or executing repository code.  It
requires installed-graph verification to be an immediate fail-stop and requires
the workspace wheel build/install to occur only after that verification.
"""

from __future__ import annotations

import argparse
import ast
import base64
import json


PRODUCT_PREP = {"build-workspace", "install-workspace"}


def _execute_name(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Name) or call.func.id != "execute" or not call.args:
        return None
    value = call.args[0]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def inspect(source: str, label: str) -> dict[str, object]:
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    calls: list[tuple[str, int, ast.Call]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and (name := _execute_name(node)):
            calls.append((name, node.lineno, node))
    calls.sort(key=lambda item: item[1])
    graph = next((item for item in calls if item[0] == "installed-graph"), None)
    if graph is None:
        return {"label": label, "pass": False, "signature": "installed-graph-missing"}

    _, graph_line, graph_call = graph
    node: ast.AST | None = graph_call
    guarded = False
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If) and graph_call in ast.walk(node.test):
            guarded = any(isinstance(x, (ast.Return, ast.Raise)) for stmt in node.body for x in ast.walk(stmt))
            break
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr, ast.stmt)):
            break

    pre = [{"name": name, "line": line} for name, line, _ in calls if name in PRODUCT_PREP and line < graph_line]
    later = [{"name": name, "line": line} for name, line, _ in calls if line > graph_line]
    passed = guarded and not pre
    reasons = []
    if not guarded:
        reasons.append("installed-graph result is not an immediate return/raise gate")
    if pre:
        reasons.append("workspace build/install occurs before installed-graph verification")
    return {
        "label": label,
        "pass": passed,
        "graph_line": graph_line,
        "graph_immediately_guarded": guarded,
        "pre_graph_product_actions": pre,
        "later_literal_execute_actions": later,
        "signature": "ok" if passed else "; ".join(reasons),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--source-base64", required=True)
    parser.add_argument("--expect", choices=("pass", "fail"), required=True)
    args = parser.parse_args()
    result = inspect(base64.b64decode(args.source_base64).decode(), args.label)
    result["expected"] = args.expect
    result["expectation_met"] = result["pass"] == (args.expect == "pass")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["expectation_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
