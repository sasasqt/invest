"""Frozen factor artifacts: everything inference needs, and nothing it may refit."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from invest_mining.expressions import OPERATOR_VERSION, canonical, features_used, lookback, parse

ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class FrozenFactor:
    expression: str  # canonical form
    orientation: int  # +1 or -1, chosen on development data only
    horizon_days: int
    training_start: str
    training_end: str  # last decision date whose label was used for selection
    dataset_id: str
    dataset_sha256: str | None
    operator_version: str = OPERATOR_VERSION
    selection: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.orientation not in (1, -1):
            raise ValueError("orientation must be +1 or -1")
        object.__setattr__(self, "expression", canonical(self.expression))

    @property
    def factor_id(self) -> str:
        key = f"{self.expression}|{self.orientation}|{self.operator_version}"
        return "f_" + hashlib.sha256(key.encode()).hexdigest()[:12]

    @property
    def lookback(self) -> int:
        return lookback(parse(self.expression))

    def to_json(self) -> dict[str, Any]:
        return {
            "artifact_version": ARTIFACT_VERSION,
            "factor_id": self.factor_id,
            "features": sorted(features_used(parse(self.expression))),
            "lookback_sessions": self.lookback,
            **asdict(self),
        }

    def save(self, path: str | os.PathLike[str]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_json(), indent=2, default=str) + "\n")
        return p

    @staticmethod
    def load(path: str | os.PathLike[str]) -> FrozenFactor:
        raw = json.loads(Path(path).read_text())
        if raw.get("artifact_version") != ARTIFACT_VERSION:
            raise ValueError(f"unsupported artifact_version {raw.get('artifact_version')!r}")
        if raw.get("operator_version") != OPERATOR_VERSION:
            raise ValueError(
                f"artifact uses operator_version {raw.get('operator_version')!r}, "
                f"this library implements {OPERATOR_VERSION!r}"
            )
        names = {f for f in FrozenFactor.__dataclass_fields__}
        factor = FrozenFactor(**{k: v for k, v in raw.items() if k in names})
        if factor.factor_id != raw.get("factor_id"):
            raise ValueError("factor_id does not match artifact content")
        return factor
