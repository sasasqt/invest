"""Classify exact-revision CI evidence using job timestamps, not attempt numbers."""

from datetime import datetime

EXPECTED_JOBS = {
    "checks (3.11)",
    "checks (3.13)",
    "wheels",
    "independent-install (data-pipeline/data-preparation)",
    "independent-install (data-mining-framework)",
    "independent-install (strategy-evaluation)",
}


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def classify(run, jobs, expected_sha, requested_after):
    if run["head_sha"] != expected_sha:
        raise ValueError("CI head differs from the audited revision")
    cutoff = instant(requested_after)
    output = []
    for name in sorted(EXPECTED_JOBS):
        candidates = [job for job in jobs if job["name"] == name]
        if not candidates:
            output.append({"name": name, "evidence": "missing"})
            continue
        unstarted = [job for job in candidates if not job.get("started_at")]
        if unstarted:
            job = max(unstarted, key=lambda item: item["id"])
            output.append(
                {
                    "name": name,
                    "job_id": job["id"],
                    "status": job["status"],
                    "conclusion": job.get("conclusion"),
                    "evidence": "pending_not_started",
                    "started_at": None,
                    "url": job.get("html_url"),
                }
            )
            continue
        job = max(candidates, key=lambda item: instant(item["started_at"]))
        fresh = instant(job["started_at"]) >= cutoff
        output.append(
            {
                "name": name,
                "job_id": job["id"],
                "status": job["status"],
                "conclusion": job.get("conclusion"),
                "evidence": "fresh" if fresh else "historical_reused",
                "started_at": job["started_at"],
                "url": job.get("html_url"),
            }
        )
    return output
