# Design by Contract Guidelines

Design by contract makes the obligations of a caller and the guarantees of an implementation explicit. Apply it to public APIs, artifact boundaries, important state transitions, and numerical routines. A contract is useful when it prevents a concrete failure or makes an assumption testable; it should not become ceremonial validation around every line of code.

The examples below are illustrative. The implemented boundaries follow these rules: bundle readers raise `BundleError`, the backtest engine raises `InputError` and `AccountingError`, and metrics return explicit statuses instead of `assert`-based checks.

## 1. Preconditions, postconditions, and invariants

- **Preconditions:** facts the caller must establish before an operation, such as a supported schema version or a valid evaluation interval.
- **Postconditions:** facts the operation guarantees on success, such as a published bundle matching its manifest or an accounting ledger reconciling.
- **Invariants:** facts that hold at valid observable states, such as unique instrument/timestamp keys or consistent cash and position accounting.
- **Failure guarantees:** what remains valid when an operation fails, including preservation of inputs, cleanup of temporary outputs, and absence of partial publication.

Document ownership: callers establish preconditions; implementations establish postconditions and preserve invariants. An implementation must not silently repair invalid caller input in ways that change meaning. Normalization or recovery is acceptable only when explicitly part of the API and recorded in the output.

Invariants describe observable states, not necessarily every intermediate instruction. Keep intermediate mutations private or transactional so consumers cannot observe invalid state.

## 2. Make contracts precise and usable

- Specify types, shapes, units, identifiers, supported versions, ordering requirements, missing-value rules, and allowed ranges.
- State semantic requirements in addition to structural ones. A timestamp can be syntactically valid yet represent information unavailable at decision time.
- Specify side effects and ownership: whether inputs are mutated, outputs are immutable, resources are opened, or persistent state changes.
- Use explicit exceptions or result statuses. Identify the offending field or violated condition without exposing sensitive values.
- Define permitted edge cases. Empty data, flat returns, constant factors, zero denominators, and insufficient samples require deliberate behavior.
- Keep contracts deterministic and inexpensive where practical. Expensive full-data checks can run at ingestion/publication boundaries rather than on every inner-loop evaluation.
- Version serialized contracts and maintain compatibility fixtures. Do not silently reinterpret an existing version.
- Keep documentation, schemas, runtime validation, and tests consistent. Select one authoritative specification for each condition rather than duplicating contradictory rules.

Type hints and static checks express part of a contract; they do not establish units, causality, numerical stability, or runtime validity by themselves.

## 3. Enforce contracts at the right layer

| Boundary | Enforcement |
|---|---|
| External files, configuration, and requests | Runtime schema/type checks and explicit semantic validation |
| Public Python API | Check caller obligations that cannot be safely assumed; document exceptions |
| Internal validated objects | Reuse established invariants; add checks where state changes can invalidate them |
| Numerical output | Check finite/valid results, tolerances, and declared undefined-result behavior |
| Persistent publication | Validate temporary outputs, then publish atomically; verify manifest identity |
| State transitions | Check legal transitions and reconcile resulting state |

Do not use Python `assert` to validate external inputs or essential production conditions: assertions may be disabled with `python -O`. Use explicit checks raising appropriate exceptions. Assertions are suitable for internal debugging assumptions whose removal does not compromise required validation, and in tests.

Use standard `ValueError` or `TypeError` for simple APIs, or a small documented exception hierarchy when consumers need to distinguish schema, compatibility, causality, and accounting errors. Catch errors only where the caller can recover meaningfully; preserve context when wrapping them.

Distinguish **invalid input** from a **valid but undefined statistic**. Invalid return data should fail validation; a valid flat series may produce a metric with `value: null`, `status: undefined`, and a reason. Follow the [metric specification](data-pipeline/strategy-evaluation/METRICS.md).

## 4. Repository contracts

| Operation | Preconditions | Postconditions / invariants |
|---|---|---|
| Publish dataset | Supported schema; valid keys/types/units; declared timing and missing-value policy | Stored rows match the manifest; publication is complete and immutable; failed publication leaves no consumable partial bundle |
| Read dataset | Supported version; paths remain inside the bundle; declared files exist | Read-only access; schema and logical types agree; failures identify incompatibility rather than silently coercing data |
| Evaluate factor AST | Valid grammar, operator types, lookbacks, feature availability, and frozen semantics | Output aligns to instrument/time keys; invalid numerical domains are handled under the declared policy; future observations cannot change earlier causal outputs |
| Train model | Explicit development splits and label intervals; allowed fit inputs; no access to confirmation feedback | Artifact records fitted transforms, schema, cutoffs, parameters, and provenance; evaluation datasets are not mutated |
| Run inference | Compatible input schema and artifact/operator versions; required historical context | Apply frozen transforms and parameters; output is aligned and timestamped; inference performs no fitting |
| Assign quantiles | Point-in-time eligibility; fixed orientation; declared cutpoints and tie rules | Disjoint partition buckets reconcile to assigned observations; separately reported extreme slices may overlap; earlier membership does not depend on future returns |
| Submit/fill orders | Information available at decision/fill times; legal order state; declared market constraints | Cash, positions, fills, fees, and equity reconcile under the ledger rules; rejected/partial fills have explicit outcomes |
| Calculate metrics | Valid observations, frequency, accounting basis, benchmark/MAR/risk-free conventions | Correct units and metadata; applicable undefined results have explicit statuses; calculation does not change strategy inputs |
| Render report | Saved metrics/tables and methodology metadata | Rendering does not rerun search or alter numerical results; plots retain units, periods, assumptions, and result statuses |

These conditions are implementation obligations, not claims that the repository already enforces them. Financial schema details still need to be finalized as described in [the architecture](docs/ARCHITECTURE.md).

## 5. Numerical contracts

- Specify exact versus approximate relationships. Identifier alignment and accounting event counts should be exact; floating-point equality often requires justified tolerances.
- Use absolute and relative tolerances with documented units and scale. A tolerance must reflect numerical error, not conceal a material accounting discrepancy.
- Validate finiteness and mathematical domains before operations where practical. Do not silently discard NaN/Inf observations or replace failed calculations with zero.
- Preserve the distinction between mathematical validity and statistical adequacy. A correlation may be computable yet unsupported by enough independent observations for a reliable conclusion.
- Use declared policies for roundoff, currency precision, decimal conversion, and conservation checks. Currency accounting may require Decimal or integer minor units, while research matrices may use floating point; the boundary conversion must be explicit.
- Do not infer annualization, units, or trade denominators from variable names or array lengths.

Illustrative implementation:

```python
from math import isclose, isfinite


def net_profit(
    start_equity: float,
    end_equity: float,
    net_external_contributions: float,
) -> float:
    """Return currency P&L; all inputs use the same currency and basis.

    Inputs may be negative where the account specification permits it.
    The caller supplies correctly classified external flows. No inputs mutate.
    """
    values = (start_equity, end_equity, net_external_contributions)
    if not all(isfinite(value) for value in values):
        raise ValueError("Equity and external flows must be finite")

    result = end_equity - start_equity - net_external_contributions
    if not isfinite(result):
        raise ArithmeticError("Net profit calculation overflowed")
    return result


def require_reconciled(actual: float, expected: float, *, abs_tol: float) -> None:
    """Require currency values to reconcile within an explicit tolerance."""
    if not isfinite(abs_tol) or abs_tol < 0:
        raise ValueError("Tolerance must be finite and nonnegative")
    if not isfinite(actual) or not isfinite(expected):
        raise ValueError("Reconciliation values must be finite")
    if not isclose(actual, expected, rel_tol=0.0, abs_tol=abs_tol):
        raise ArithmeticError("Accounting reconciliation failed")
```

A runtime check cannot infer whether a float is USD or CNY, or whether a flow was classified correctly. Use typed/configured domain objects and provenance to establish those semantic obligations at the boundary.

## 6. Substitution and extensibility

Implementations of a common interface must honor the same contract:

- Do not strengthen preconditions: an adapter must accept every input the interface promises, or advertise a separate capability before selection.
- Do not weaken postconditions: a replacement must preserve alignment, causal behavior, status meanings, and failure guarantees promised by the interface.
- Preserve invariants and permitted state transitions. Avoid implementations that mutate inputs when the interface promises read-only behavior.
- Represent capability differences explicitly, such as derivative support, accepted storage formats, or intratrade marks. Do not discover unsupported capabilities only after a long run.

Prefer composition and small `Protocol` interfaces to a broad inheritance hierarchy. A versioned public contract utility can be shared without coupling consumers to another component's private implementation. Keep framework-specific exceptions or data types out of portable artifact schemas.

## 7. Contract testing

- Test both accepted inputs and violated preconditions, including boundaries and failure guarantees.
- Verify postconditions independently of the implementation where possible, using reference calculations and golden fixtures.
- Run the same contract suite against each interchangeable reader, writer, strategy adapter, or factor evaluator.
- Use property-based testing when it adds value: round-trip serialization, key alignment, valid AST generation, and accounting identities.
- Use metamorphic tests for financial semantics: future-data changes cannot affect earlier signals; a deposit alone cannot create profit; exported/reloaded frozen inference agrees with the original predictor.
- Test atomic publication failures, cleanup, retry/idempotency assumptions, and unchanged caller-owned inputs.
- Exercise essential checks under `python -O` when there is a risk that required validation was accidentally implemented with assertions.
- Keep statistical calibration tests separate from deterministic contracts. A statistical test can fail by chance; do not encode “this random null sample must never be significant” as an invariant.

Contracts do not replace unit, integration, property, regression, or statistical tests. A schema-valid artifact can still have wrong business meaning, and a correct formula can still have no useful financial effect.

## 8. Review checklist

For each new boundary or stateful operation, ask:

1. What must the caller establish, and where is that verified?
2. What is guaranteed on success, and what remains valid on failure?
3. Which invariants, units, timing rules, and side effects apply?
4. How are empty, undefined, unsupported, and insufficient-data cases distinguished?
5. Can another implementation satisfy the same interface without hidden dependencies?
6. Which independent tests demonstrate the guarantees?

Implement the smallest explicit contract needed by the current workflow, then extend it through reviewed versions. Follow [Python guidelines](PYTHON_GUIDELINES.md) and [Git guidelines](GIT_GUIDELINES.md) when implementing and changing contracts.
