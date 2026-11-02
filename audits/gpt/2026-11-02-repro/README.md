# Reproduction and limits

Source: 90b5ca038155b97833b120baa57dfecd05d6f641. This run used trusted AST/TOML/hash parsing, bash -n, and uv metadata-only lock checking. It did not import project code. `static_checks.py` requires hash-verified allowed source files under source/ and the manifest under evidence/main-tree.json in the same working layout. `build_report.py` is a generator tied to the prior-output inputs identified in identity.json, not a standalone source downloader. Fetch prior blobs from 606eae209af0d426aaf83280585e1afaca3b4084, plus the two semantic-continuation JSON files. Never use the output branch's source as current main.

To repeat runtime checks, first establish a credential-free enforced filesystem/network/process boundary, prove sentinel denials and permitted writes, then verify all source bytes and the installed locked graph. The available runner PR32 was read, not dispatched. No host isolation was established here.

The original same-SHA CI excerpts retain exact failure signatures and interpreter versions; they are historical remote evidence, not fresh local tests. Full original logs remain at the linked GitHub jobs. No datasets or copyrighted papers are included.
