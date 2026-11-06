"""Check a release tag and write its release notes from CHANGELOG.md.

Run by `.github/workflows/release.yml` when a tag like `v0.1.0` is pushed:

    python scripts/release_notes.py v0.1.0 --output notes.md

It stops with an error (exit 1) if the tag isn't `v` followed by the version
in `pyproject.toml`, or if `CHANGELOG.md` has no section for that version
(`## [0.1.0] - <date>`) or the section has no entries. Otherwise it writes
the section's body, without its heading, to the output file.

Not part of the `tskmngr` package, so it isn't shipped in the wheel; standard
library only.
"""

import argparse
import re
import sys
import tomllib
from pathlib import Path


class ReleaseError(Exception):
    """The tag, version or changelog isn't ready for a release."""


def project_version(pyproject: str) -> str:
    """Return `[project] version` from the text of a `pyproject.toml`."""
    try:
        version = tomllib.loads(pyproject)["project"]["version"]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise ReleaseError(
            f"pyproject.toml has no [project] version: {error}"
        ) from error
    if not isinstance(version, str):
        raise ReleaseError("pyproject.toml's [project] version isn't a string")
    return version


def check_tag(tag: str, version: str) -> None:
    """Stop unless the tag is `v` followed by exactly the version."""
    if tag != f"v{version}":
        raise ReleaseError(
            f"tag {tag} doesn't match the version in pyproject.toml "
            f"({version}); expected tag v{version}"
        )


def changelog_section(changelog: str, version: str) -> str:
    """Return the body of the changelog's `## [version]` section.

    The section runs from its heading to the next `## ` heading or the end of
    the file. A missing section, or one with nothing but `###` category
    headings and blank lines, is an error.
    """
    heading = re.compile(rf"^## \[{re.escape(version)}\](?:\s|$)")
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ReleaseError(
            f"CHANGELOG.md has no section for {version}; rename [Unreleased] "
            f"to [{version}] - <date> before tagging"
        )
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    body = lines[start + 1 : end]
    if not any(line.strip() and not line.startswith("#") for line in body):
        raise ReleaseError(f"CHANGELOG.md's section for {version} has no entries")
    return "\n".join(body).strip() + "\n"


def release_notes(tag: str, pyproject: str, changelog: str) -> str:
    """Check the tag against the version and return its release notes."""
    version = project_version(pyproject)
    check_tag(tag, version)
    return changelog_section(changelog, version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="the release tag, e.g. v0.1.0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    args = parser.parse_args(argv)
    try:
        notes = release_notes(
            args.tag,
            args.pyproject.read_text(encoding="utf-8"),
            args.changelog.read_text(encoding="utf-8"),
        )
    except (ReleaseError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.write_text(notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
