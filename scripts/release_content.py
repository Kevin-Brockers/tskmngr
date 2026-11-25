"""Check that a release's archives leave out the project's working files.

Run by `.github/workflows/release.yml` after `uv build`, on the wheel, the
sdist and a `git archive` of the tagged commit (what GitHub's "Source code"
archives are made from):

    python scripts/release_content.py dist/*.whl dist/*.tar.gz source.tar.gz

It stops with an error (exit 1), naming each archive and file, if one of
them holds a file in `LEFT_OUT`. `uv build` only packs the package, the
README, the license and `pyproject.toml`; `.gitattributes` leaves the files
out of `git archive` with `export-ignore`. `dev` and `main` keep them all.

Not part of the `tskmngr` package, so it isn't shipped in the wheel; standard
library only.
"""

import argparse
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

# The project's working files, at the repository's root: a release leaves them
# out. A name ending in `/` is a folder, with everything in it.
LEFT_OUT = ("AGENTS.md", "ROADMAP.md", "docs/finished_roadmap.md", ".claude/")


def archive_names(path: Path) -> list[str]:
    """The paths in the archive at `path`, from the repository's root.

    A wheel (`.whl`, a zip) holds them as they are; a `.tar.gz` (the sdist,
    or a `git archive` with a prefix) has them in one top folder, dropped
    here.
    """
    if path.name.endswith(".whl") or path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path) as archive:
        names = [member.name for member in archive.getmembers()]
    return [
        str(PurePosixPath(*parts[1:]))
        for parts in (PurePosixPath(name).parts for name in names)
        if len(parts) > 1
    ]


def left_out_names(names: Iterable[str]) -> list[str]:
    """The names in `names` that a release must leave out (see `LEFT_OUT`)."""
    found = []
    for name in names:
        for left_out in LEFT_OUT:
            if left_out.endswith("/"):
                if name.startswith(left_out) or name == left_out.rstrip("/"):
                    found.append(name)
                    break
            elif name == left_out:
                found.append(name)
                break
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archives", nargs="+", type=Path, metavar="ARCHIVE")
    args = parser.parse_args(argv)
    status = 0
    for path in args.archives:
        for name in left_out_names(archive_names(path)):
            print(f"error: {path} holds {name}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
