"""Audit-only standard-library control. Never imports or executes repository code."""
import hashlib
import json
import math

def invalid_constant(token):
    raise ValueError(token)

def finite_float(token):
    number = float(token)
    if not math.isfinite(number):
        raise ValueError(token)
    return number

for repeat in (1, 2):
    for token in ("NaN", "Infinity", "-Infinity", "1e999", "null", "0.125"):
        literal = '{"trial_stat": ' + token + '}'
        legacy = json.dumps(json.loads(literal), sort_keys=True)
        digest = hashlib.sha256(legacy.encode()).hexdigest()
        try:
            strict = json.loads(literal, parse_constant=invalid_constant, parse_float=finite_float)
            json.dumps(strict, allow_nan=False)
            observed = "accepted"
        except ValueError:
            observed = "rejected"
        assert observed == ("accepted" if token in ("null", "0.125") else "rejected")
        print(repeat, token, "default accepted", digest, "finite policy", observed)
    good1, good2 = '{"y": 2, "x": null}', '{"x":null,"y":2}'
    canonical = lambda text: json.dumps(json.loads(text), sort_keys=True)
    assert canonical(good1) == canonical(good2)
    assert canonical(good1) != canonical('{"y": 3, "x": null}')
    print(repeat, "finite key-order control equal; substantive change differs")
