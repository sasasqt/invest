# Rechecking the original remote evidence

The two JSON transfer inputs beside `verify_remote_evidence.py` contain public Git identities and canonical encoded runner/lock metadata. They contain no credential or raw observation. The script never imports product modules.

Place artifact `13224610191` from run `41620332472` beside the script as `audit-audited-3.11.zip`; its expected SHA-256 is in `remote-evidence.json`. Fetch `uv.lock` at product commit `9913f94b9b795bd9633a6a683e9f420301e400b3` beside the script as `uv.lock` (SHA-256 `4e14019237eefe5b318cfe68f5544729838566abfae279a75ba4d4b6b7eaa330`). Run the trusted script with Python 3.11+ and its standard library. No builds or dependency installs are involved.

The script checks expected reported dependency versions, including both multi-version lock branches, without executing marker expressions from repository text. The original runner's marker-aware verifier also reported exit 0. This does not inventory all unexpected installed distributions; that remains a qualification check.

The raw archive is available through GitHub's expiring artifact retention, so its original ID, digest and timings are preserved here. Its entire ZIP is not transplanted into the audit output branch. The compact sanitized records and independently derived arithmetic scripts remain accessible after expiration.
