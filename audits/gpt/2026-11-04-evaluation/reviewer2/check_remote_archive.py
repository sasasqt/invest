"""Read-only independent ZIP/JSON/hash checks of an already completed CI run.
No import or execution of repository/runner code; this is evidence inspection.
"""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tomllib
import zipfile

ROOT = Path(__file__).parent.parent
EXPECTED_ZIP = "e415cc213f7efc475e017e6794b4b67722422f47dac9ab469322ce51ee3050bb"
SOURCE = "9913f94b9b795bd9633a6a683e9f420301e400b3"
HEAD = "e0181fcbfda9814c53bccec4d0f1d5294487ec2d"
PREVIEW = "e01768fa81d08530021fef441f66c65a72ec78be"


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


data = (ROOT / "audit-audited-3.11.zip").read_bytes()
assert hashlib.sha256(data).hexdigest() == EXPECTED_ZIP
transfer = json.loads((ROOT.parent / "wed-runtime-transfer.json").read_text())
main_blobs = json.loads((Path(__file__).parent / "fresh-main-blobs.json").read_text())
head_tree, preview_tree = transfer["runnerTree"], transfer["previewTree"]
assert head_tree["sha"] == HEAD and preview_tree["sha"] == PREVIEW
runner_paths = lambda tree: {
    e["path"]: (e["sha"], e["mode"])
    for e in tree["tree"]
    if e["type"] == "blob" and
    (e["path"].startswith("audits/gpt/runner/") or e["path"] == ".github/workflows/audit-runtime.yml")
}
runner, preview = runner_paths(head_tree), runner_paths(preview_tree)
assert runner == preview and len(runner) == 17
for key, path in [("installedVerifier", "audits/gpt/runner/verify_installed.py"),
                  ("workflow", ".github/workflows/audit-runtime.yml")]:
    assert git_blob(base64.b64decode(transfer[key])) == runner[path][0]
workload = base64.b64decode((Path(__file__).parent / "runner-workload-base64.txt").read_text())
assert git_blob(workload) == runner["audits/gpt/runner/runner_workload.py"][0]
lockbytes = base64.b64decode(transfer["lock"])
assert git_blob(lockbytes) == main_blobs["uv.lock"]
lock = tomllib.loads(lockbytes.decode())

with zipfile.ZipFile(ROOT / "audit-audited-3.11.zip") as z:
    names = z.namelist()
    assert len(names) == len(set(names))
    for item in z.infolist():
        p = PurePosixPath(item.filename)
        assert not p.is_absolute() and ".." not in p.parts and not stat.S_ISLNK(item.external_attr >> 16)
    read_json = lambda p: json.loads(z.read(p))
    source = read_json("source-identity.json")
    assert source["sha"] == SOURCE
    actual_source = {e["path"]: e["git_blob"] for e in source["files"]}
    assert actual_source == main_blobs and len(actual_source) == 111
    run = read_json("runner.json")
    assert run["sha"] == SOURCE and run["exit"] == 0 and run["collection_status"] == "collected"
    launch = read_json("launch.json")
    assert launch["sha"] == SOURCE and launch["image_id"] == run["image_id"]
    command = launch["command"]
    for flag in ["--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                 "--pids-limit=256", "--memory=2g", "--cpus=2"]:
        assert flag in command
    assert command[command.index("--user") + 1] == "1001:1001"
    for proxy in ["HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY", "NO_PROXY"]:
        assert proxy + "=" in command and proxy.lower() + "=" in command
    boundary = read_json("workload/boundary.json")
    assert len(boundary) == 12 and all(v is True for v in boundary.values())
    env = read_json("workload/environment.json")
    assert env["lock_sha256"] == hashlib.sha256(lockbytes).hexdigest()
    assert env["python"].startswith("3.11.18") and env["platform"].startswith("Linux-")
    collection = read_json("collection.json")
    assert collection["status"] == "collected" and collection["entries"] == 46
    listed = {"workload/" + e["path"]: e for e in collection["files"]}
    archive_workload = {n for n in names if n.startswith("workload/")}
    assert set(listed) == archive_workload
    for name, entry in listed.items():
        content = z.read(name)
        assert len(content) == entry["bytes"] and hashlib.sha256(content).hexdigest() == entry["sha256"]
    steps = [json.loads(line) for line in z.read("workload/validation.jsonl").decode().splitlines()]
    assert len(steps) == 32 and all(s["exit"] == 0 and s["timeout"] is False for s in steps)
    rootsteps = [json.loads(line) for line in z.read("execution.log").decode().splitlines()]
    assert steps == rootsteps
    installed = read_json("workload/installed-graph.log")
    assert len(installed["resolved"]) == 26
    for dist in installed["resolved"]:
        choices = [p for p in lock["package"] if p["name"] == dist["name"] and p["version"] == dist["version"]]
        assert choices, dist
        # Only contourpy/numpy have alternate versions here; inspect marker branches.
        for choice in choices:
            markers = choice.get("resolution-markers", [])
            if markers:
                assert any(m == "python_full_version < '3.12' and sys_platform != 'emscripten' and sys_platform != 'win32'" for m in markers), dist
    assert all(p.startswith("/work/env/lib/python3.11/site-packages/") for p in installed["origins"].values())
    log_counts = {}
    for name, count in [("tests", 652), ("hash-seed-repeat", 652), ("strategy-evaluation-tests", 289)]:
        text = z.read("workload/" + name + ".log").decode()
        assert re.search(r"\b" + str(count) + r" passed\b", text)
        log_counts[name] = count
    results = {"zip_sha256": EXPECTED_ZIP, "source_sha": SOURCE,
               "source_manifest_entries_match_fresh_main": len(actual_source),
               "runner_head": HEAD, "actual_runner_checkout": PREVIEW,
               "runner_workflow_blob_and_mode_matches": len(runner),
               "workload_manifest_file_hashes_verified": len(listed),
               "boundary_checks_true": len(boundary), "reported_expected_distributions_match_lock": len(installed["resolved"]),
               "relevant_versions": {d["name"]: d["version"] for d in installed["resolved"]
                                     if d["name"] in ("numpy", "pandas", "pyarrow", "pytest", "packaging")},
               "original_validation_stages_exit0_no_timeout": len(steps),
               "observed_log_pass_counts": log_counts, "environment": env}
print(json.dumps(results, indent=2))
