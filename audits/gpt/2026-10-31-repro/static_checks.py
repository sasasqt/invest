"""Trusted audit-only parser. Never imports or executes repository modules."""
import ast
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'source'
OUT = ROOT / 'outputs/audits/gpt/2026-10-31-repro'
OUT.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
manifest = json.loads((ROOT / 'remote-manifest.json').read_text())
rows, imports, leads, shell = [], [], [], []
for entry in manifest['tree']:
    if entry['type'] != 'blob':
        continue
    path = entry['path']
    target = SOURCE / path
    data = target.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    assert blob == entry['sha'] and len(data) == entry['size'], path
    text = None if path.endswith('.png') else data.decode('utf-8')
    row = dict(path=path, blob_sha=blob, bytes=len(data), lines=None if text is None else len(text.splitlines()), checks=['blob_identity'])
    if path.endswith('.py'):
        tree = ast.parse(text, filename=path)
        row['checks'].append('ast_parse')
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(dict(path=path, line=node.lineno, module=a.name, relative=False) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(dict(path=path, line=node.lineno, module=node.module, relative=bool(node.level)))
            elif isinstance(node, ast.Call):
                method = node.func.attr if isinstance(node.func, ast.Attribute) else None
                if method in ('read_text', 'write_text') and not any(k.arg=='encoding' for k in node.keywords):
                    leads.append(dict(path=path,line=node.lineno,kind='implicit_text_encoding',confidence='pattern_only'))
    if path.endswith('.sh'):
        p = subprocess.run(['/usr/bin/bash','-n',str(target)],capture_output=True,text=True,timeout=60)
        shell.append(dict(path=path,command='bash -n '+path,exit_code=p.returncode,stderr=p.stderr,set_euo_pipefail='set -euo pipefail' in text))
        row['checks'].append('bash_n')
    if path.endswith('.toml') or path=='uv.lock':
        tomllib.loads(text)
        row['checks'].append('toml_parse')
    if path.startswith('runs/') and path.endswith('/manifest.json'):
        # Metadata schema shape only; do not inspect saved market observations or derived tables.
        value=json.loads(text)
        row['checks'].append('saved_manifest_json_parse')
    rows.append(row)
lock=tomllib.loads((SOURCE/'uv.lock').read_text())
manifests={str(p.relative_to(SOURCE)):tomllib.loads(p.read_text()) for p in SOURCE.rglob('pyproject.toml')}
packages=[]
for path,m in manifests.items():
    project=m['project']; match=[p for p in lock['package'] if p['name']==project['name']]
    packages.append(dict(path=path,name=project['name'],python=project['requires-python'],dependencies=project.get('dependencies'),locked_workspace_matches=len(match),entry_points=project.get('scripts',{})))
result=dict(sha='90b5ca038155b97833b120baa57dfecd05d6f641',inventory=rows,imports=imports,portability_leads=leads,shell_checks=shell,workspace_packages=packages,lock_python=lock['requires-python'],submodules=[e for e in manifest['tree'] if e['mode']=='160000'],symlinks=[e for e in manifest['tree'] if e['mode']=='120000'],lfs_pointer_paths=[r['path'] for r in rows if r['bytes']<2000 and (SOURCE/r['path']).read_bytes().startswith(b'version https://git-lfs.github.com/spec/')],elapsed_seconds=time.monotonic()-started,limitations=['AST import inventory does not verify independent installation','TOML parse does not run uv lock --check or verify installed graph','No repository code executed'])
(OUT/'static-checks.json').write_text(json.dumps(result,indent=2))
print(json.dumps(dict(files=len(rows),python_files=sum('ast_parse' in r['checks'] for r in rows),shell=shell,portability_pattern_count=len(leads),workspace=packages,elapsed_seconds=result['elapsed_seconds'])))
