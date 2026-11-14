"""Standalone gzip library control, with no product imports."""

import gzip
from io import BytesIO

for _ in range(2):
    controls = (
        (b"", b""),
        (gzip.compress(b"", mtime=0), b""),
        (gzip.compress(b"id\n7\n", mtime=0), b"id\n7\n"),
    )
    for raw, expected in controls:
        with gzip.GzipFile(fileobj=BytesIO(raw), mode="rb") as stream:
            assert stream.read() == expected
    try:
        with gzip.GzipFile(fileobj=BytesIO(b"not gzip"), mode="rb") as stream:
            stream.read()
    except gzip.BadGzipFile:
        pass
    else:
        raise AssertionError("a non-gzip header should fail")
print("Two control repetitions passed")
