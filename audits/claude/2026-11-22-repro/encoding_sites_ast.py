"""AST count of text I/O calls without encoding= (read_text, write_text, open in text mode) per file, at two revisions.
Usage: python encoding_sites_ast.py <repo worktree> <old sha> <new sha> <path> [<path> ...]  (reads blobs with git show)."""
import ast, subprocess, sys
repo, old, new, paths = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
def sites(src):
    out = []
    try: tree = ast.parse(src)
    except SyntaxError: return ["<syntax error>"]
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call): continue
        kw = {k.arg for k in n.keywords}
        name = n.func.attr if isinstance(n.func, ast.Attribute) else (n.func.id if isinstance(n.func, ast.Name) else None)
        if name in ("read_text", "write_text") and "encoding" not in kw:
            out.append(f"{n.lineno}:{name}")
        elif name == "open" and "encoding" not in kw:
            mode = None
            if len(n.args) >= 2 and isinstance(n.args[1], ast.Constant): mode = n.args[1].value
            for k in n.keywords:
                if k.arg == "mode" and isinstance(k.value, ast.Constant): mode = k.value.value
            if mode is None or "b" not in str(mode):
                out.append(f"{n.lineno}:open({mode!r})")
    return out
total = [0, 0]
for p in paths:
    res = []
    for i, rev in enumerate((old, new)):
        r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{p}"], capture_output=True, text=True)
        s = sites(r.stdout) if r.returncode == 0 else []
        res.append(s); total[i] += len(s)
    print(f"{p}: {old[:7]} {len(res[0])} -> {new[:7]} {len(res[1])}; new sites: {sorted(set(res[1]) - set(res[0]))[:12]}")
print("total", total, "delta", total[1] - total[0])
