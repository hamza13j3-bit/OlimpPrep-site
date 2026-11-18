"""Zip a problem folder into a package the importer accepts.

    python make_zip.py <folder> <out.zip>

Use this instead of Windows "Send to > Compressed folder" / Compress-Archive, which can
write backslash paths that the importer rejects.
"""

import sys
import zipfile
from pathlib import Path


def main(folder: str, out: str) -> None:
    root = Path(folder)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix != ".zip" and path.name != "make_zip.py" and path.name != "README.md":
                zf.write(path, path.relative_to(root).as_posix())
    print(f"wrote {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
