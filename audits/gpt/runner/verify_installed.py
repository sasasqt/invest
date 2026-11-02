"""Verify applicable locked distribution versions inside the execution container."""

import argparse
import importlib.metadata as metadata
import importlib.util
import json
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement


def applicable_requirements(text, environment=None):
    result = []
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(re.sub(r"\s+--hash=\S+", "", line))
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        result.append(requirement)
    return result


def verify_versions(requirements, lookup):
    result = []
    for requirement in requirements:
        version = lookup(requirement.name)
        if version not in requirement.specifier:
            raise ValueError(
                f"{requirement.name}: installed {version}; expected {requirement.specifier}"
            )
        result.append({"name": requirement.name, "version": version})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--workspace-prefix", required=True)
    args = parser.parse_args()
    graph = verify_versions(
        applicable_requirements(Path(args.requirements).read_text()), metadata.version
    )
    origins = {}
    for name in ("invest_data", "invest_mining", "invest_evaluation"):
        spec = importlib.util.find_spec(name)
        if not spec or not spec.origin or not spec.origin.startswith(args.workspace_prefix):
            raise ValueError(f"Wrong installed workspace origin for {name}: {spec}")
        origins[name] = spec.origin
    print(json.dumps({"resolved": graph, "origins": origins, "python": sys.version}, indent=2))


if __name__ == "__main__":
    main()
