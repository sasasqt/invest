"""Like-for-like portability comparison: same scanner on the previous audited SHA and on main. Args: <worktree> <old sha> <out file>."""
import re, subprocess, sys, json
root, old, outf = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, "")
RULES = {
 "read_write_text_no_encoding": re.compile(r"\.(read_text|write_text)\((?![^)]*encoding=)[^)]*\)"),
 "open_no_encoding": re.compile(r"(?<![\w.])open\((?![^)]*encoding=)(?![^)]*['\"][rwax+]*b[rwax+]*['\"])[^)]*\)"),
 "os_rename": re.compile(r"\bos\.rename\("),
 "python_literal_in_call": re.compile(r"\[\s*['\"]python3?['\"]"),
 "csv_writer_no_lineterminator": re.compile(r"csv\.writer\((?![^)]*lineterminator)"),
 "tmp_literal": re.compile(r"['\"]/tmp\b"),
 "posix_module_import": re.compile(r"^\s*(import|from)\s+(fcntl|pwd|resource|grp|termios)\b", re.M),
}
def scan(t):
    c = {k: len(rx.findall(t)) for k, rx in RULES.items()}
    c["path_rename"] = len([m for m in re.finditer(r"\.rename\(", t) if not t[max(0,m.start()-3):m.start()].endswith("os")])
    return c
changed = subprocess.run(["git","-C",root,"diff","--name-only",old,"HEAD","--","*.py"],capture_output=True,text=True).stdout.split()
res = {}
for f in changed:
    o = subprocess.run(["git","-C",root,"show",f"{old}:{f}"],capture_output=True,text=True)
    oc = scan(o.stdout) if o.returncode == 0 else {k:0 for k in list(RULES)+["path_rename"]}
    try: nt = open(f"{root}/{f}", encoding="utf-8").read(); nc = scan(nt)
    except FileNotFoundError: nc = {k:0 for k in oc}
    diff = {k: (oc[k], nc[k]) for k in nc if nc[k] != oc[k]}
    if diff: res[f] = {"new_file": o.returncode != 0, "changes": diff}
open(outf, "w", encoding="utf-8").write(json.dumps(res, indent=1, sort_keys=True))
for f, d in sorted(res.items()):
    print(f, "(new file)" if d["new_file"] else "", {k: f"{a}->{b}" for k,(a,b) in d["changes"].items()})
