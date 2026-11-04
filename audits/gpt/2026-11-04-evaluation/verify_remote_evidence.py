"""Verify downloaded existing CI evidence; does not execute repository code."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tomllib
import zipfile

root = Path(__file__).resolve().parent
input_root = root if (root/'wed-source-transfer.json').exists() else root.parent
transfer = json.loads((input_root / 'wed-source-transfer.json').read_text())
runtime = json.loads((input_root / 'wed-runtime-transfer.json').read_text())
archive = root / 'audit-audited-3.11.zip'
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
assert digest == 'e415cc213f7efc475e017e6794b4b67722422f47dac9ab469322ce51ee3050bb'
z = zipfile.ZipFile(archive)
for entry in z.infolist():
    p = PurePosixPath(entry.filename)
    assert not p.is_absolute() and '..' not in p.parts
    assert (entry.external_attr >> 16) & 0o170000 != 0o120000
def read(name):
    return json.loads(z.read(name))
source = read('source-identity.json')
expected = {e['path']:e['sha'] for e in transfer['inventory']['tree'] if e['type']=='blob'}
actual = {e['path']:e['git_blob'] for e in source['files']}
assert actual == expected
trees = [{e['path']:e for e in runtime[k]['tree']} for k in ['runnerTree','previewTree']]
runner_paths = [p for p in trees[0] if p.startswith('audits/gpt/runner/') and trees[0][p]['type']=='blob']
runner_paths += ['.github/workflows/audit-runtime.yml']
assert all(trees[0][p]['sha'] == trees[1][p]['sha'] for p in runner_paths)
collection = read('collection.json')
for f in collection['files']:
    b = z.read('workload/' + f['path'])
    assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256']
lock_path=root/'runner-read/lock.txt'
if not lock_path.exists():
    lock_path=root/'uv.lock'
lock_bytes=lock_path.read_bytes()
environment=read('workload/environment.json')
assert hashlib.sha256(lock_bytes).hexdigest()==environment['lock_sha256']
lock=tomllib.loads(lock_bytes.decode())
versions={}
for x in lock['package']:
    versions.setdefault(x['name'].replace('_','-').lower(),set()).add(x['version'])
installed=read('workload/installed-graph.log')
assert all(x['version'] in versions[x['name'].replace('_','-').lower()] for x in installed['resolved'])
for name in ['numpy','contourpy']:
    selected=next(x for x in installed['resolved'] if x['name']==name)
    package=next(x for x in lock['package'] if x['name']==name and x['version']==selected['version'])
    assert "python_full_version < '3.12' and sys_platform != 'emscripten' and sys_platform != 'win32'" in package['resolution-markers']
boundary=read('workload/boundary.json');assert all(v is True for v in boundary.values())
validation=[json.loads(x) for x in z.read('workload/validation.jsonl').decode().splitlines()]
assert all(x['exit']==0 and not x['timeout'] for x in validation)
manifest_bytes=[z.read(f'workload/synth-S-{i}-semantic-manifest.json') for i in range(8)]
assert len(set(manifest_bytes))==1
summary={'source_sha':source['sha'],'runner_head':'e0181fcbfda9814c53bccec4d0f1d5294487ec2d',
 'actual_runner_checkout':'e01768fa81d08530021fef441f66c65a72ec78be','runner_workflow_blob_matches':len(runner_paths),
 'workflow_run':41620332472,'job':125864532791,'started_utc':'2026-11-03T10:34:57Z','completed_utc':'2026-11-03T10:46:12Z',
 'artifact_id':13224610191,'artifact_sha256':digest,'archive_digest_matches':True,
 'source_inventory_matches':len(actual),'collected_files_hash_verified':len(collection['files']),
 'boundary_controls':boundary,'environment':environment,'installed_versions':installed,
 'installed_graph_scope':'all 26 reported resolved distributions match lock; original marker-aware verifier exit0. No local/native environment installed here.',
 'validation_commands':validation,'test_result':'652 passed in 279.72s',
 'repeat_result':z.read('workload/hash-seed-repeat.log').decode()[-220:],
 'independent_evaluation_result':z.read('workload/strategy-evaluation-tests.log').decode()[-230:],
 'synthetic_semantic_manifests_equal':True,'synthetic_semantic_manifest_entries':len(json.loads(manifest_bytes[0])),
 'scope':'Existing remote evidence from Nov3; freshly downloaded and verified Nov4. No new workflow/product execution, custom drawdown fixture, full hostile-host certification, historical replay or matched performance comparison.',
 'limits':'Observed host canary/child/filesystem/network/process controls apply to this run. Host metadata source reads and disk quota limits remain; local execution and native Windows Docker not established.'}
(root/'remote-evidence.json').write_text(json.dumps(summary,indent=2)+'\n')
for name in ['workload/boundary.json','workload/environment.json','workload/installed-graph.log','workload/coverage.json']:
    p=root/'remote-checked'/name.removeprefix('workload/');p.parent.mkdir(exist_ok=True);p.write_bytes(z.read(name))
print(json.dumps({k:v for k,v in summary.items() if k not in ['validation_commands','installed_versions']},indent=2))
