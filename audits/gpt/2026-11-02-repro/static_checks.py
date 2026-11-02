"""Trusted audit parser. Never imports or executes project modules."""
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'source'
t0 = time.monotonic()
report = {'sha': '90b5ca038155b97833b120baa57dfecd05d6f641', 'ast': [], 'toml': [], 'shell': [], 'imports': [], 'portability_leads': [], 'local_links': []}
for path in sorted(source.rglob('*')):
    if not path.is_file():
        continue
    rel = path.relative_to(source).as_posix()
    if path.suffix == '.py':
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=rel)
        tests = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')]
        report['ast'].append({'path': rel, 'status': 'parsed', 'test_functions': len(tests), 'test_functions_without_ast_assert': [n.name for n in tests if not any(isinstance(k, ast.Assert) for k in ast.walk(n))]})
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or '']
                report['imports'].extend({'path': rel, 'line': n.lineno, 'module': name, 'relative_level': getattr(n, 'level', 0)} for name in names)
            if isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ''
                if name in {'read_text', 'write_text', 'open'} and not any(k.arg == 'encoding' for k in n.keywords):
                    report['portability_leads'].append({'path': rel, 'line': n.lineno, 'lead': 'text I/O without explicit encoding; binary/mode/context need semantic review'})
    elif path.suffix in {'.toml', '.lock'}:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
        report['toml'].append({'path': rel, 'status': 'parsed', 'python': data.get('project', {}).get('requires-python'), 'dependencies': data.get('project', {}).get('dependencies'), 'scripts': data.get('project', {}).get('scripts')})
    elif path.suffix == '.sh':
        t = time.monotonic()
        proc = subprocess.run(['bash', '-n', str(path)], capture_output=True, text=True, timeout=60)
        report['shell'].append({'path': rel, 'command': ['bash', '-n', rel], 'exit': proc.returncode, 'stderr': proc.stderr, 'seconds': time.monotonic()-t})
    if path.suffix == '.md':
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)', line):
                if target.startswith(('http:', 'https:', 'mailto:', '#')):
                    continue
                target = target.split('#')[0]
                if not target:
                    continue
                dest = path.parent / target
                present = dest.exists()
                manifest = json.loads((root / 'evidence/main-tree.json').read_text())['tree']
                # Manifest membership distinguishes deliberately omitted saved files.
                import os
                logical = os.path.normpath(str(dest.relative_to(source)))
                in_manifest = any(x['path'] == logical for x in manifest)
                if not present and not in_manifest:
                    report['local_links'].append({'path': rel, 'line': n, 'target': target, 'status': 'needs review; regex not Markdown parser'})
report['elapsed_seconds'] = time.monotonic()-t0
(root / 'evidence/static-checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'python_files_parsed': len(report['ast']), 'test_functions': sum(x['test_functions'] for x in report['ast']), 'manifest_files_parsed': len(report['toml']), 'shell': report['shell'], 'possible_links': report['local_links'], 'portability_leads': len(report['portability_leads']), 'elapsed_seconds': report['elapsed_seconds']}, indent=2))
