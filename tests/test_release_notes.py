"""Tests for `scripts/release_notes.py`, used by the release workflow."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "release_notes.py"
_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert _spec is not None and _spec.loader is not None
release_notes = importlib.util.module_from_spec(_spec)
sys.modules["release_notes"] = release_notes
_spec.loader.exec_module(release_notes)

ReleaseError = release_notes.ReleaseError

PYPROJECT = '[project]\nname = "tskmngr"\nversion = "0.1.0"\n'

CHANGELOG = """\
# Changelog

Intro text.

## [Unreleased]

### Added

- [#90](https://example.com/90) - Something not released yet

## [0.1.0] - 2026-11-15

### Added

- [#5](https://example.com/5) - Package skeleton
- [#8](https://example.com/8) - Task model,
  over two lines

### Fixed

- [#14](https://example.com/14) - A fix

## [0.0.9] - 2026-01-01

### Added

- An older entry
"""


def test_project_version() -> None:
    assert release_notes.project_version(PYPROJECT) == "0.1.0"


@pytest.mark.parametrize(
    "text",
    ['[project]\nname = "x"\n', "not toml [", "[project]\nversion = 1\n", ""],
)
def test_project_version_missing_or_invalid(text: str) -> None:
    with pytest.raises(ReleaseError, match="version"):
        release_notes.project_version(text)


def test_check_tag_matches() -> None:
    release_notes.check_tag("v0.1.0", "0.1.0")


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1.1", "v0.1.0.dev0", "v0.1", "V0.1.0"])
def test_check_tag_mismatch(tag: str) -> None:
    with pytest.raises(ReleaseError, match="expected tag v0.1.0"):
        release_notes.check_tag(tag, "0.1.0")


def test_changelog_section_between_headings() -> None:
    assert release_notes.changelog_section(CHANGELOG, "0.1.0") == (
        "### Added\n"
        "\n"
        "- [#5](https://example.com/5) - Package skeleton\n"
        "- [#8](https://example.com/8) - Task model,\n"
        "  over two lines\n"
        "\n"
        "### Fixed\n"
        "\n"
        "- [#14](https://example.com/14) - A fix\n"
    )


def test_changelog_section_runs_to_end_of_file() -> None:
    assert release_notes.changelog_section(CHANGELOG, "0.0.9") == (
        "### Added\n\n- An older entry\n"
    )


def test_changelog_section_without_date() -> None:
    changelog = "## [0.1.0]\n\n- Entry\n"
    assert release_notes.changelog_section(changelog, "0.1.0") == "- Entry\n"


def test_changelog_section_missing() -> None:
    with pytest.raises(ReleaseError, match=r"no section for 0\.2\.0.*\[Unreleased\]"):
        release_notes.changelog_section(CHANGELOG, "0.2.0")


def test_changelog_section_only_unreleased() -> None:
    """Before the release PR renames [Unreleased], there's no section."""
    changelog = "# Changelog\n\n## [Unreleased]\n\n- Entry\n"
    with pytest.raises(ReleaseError, match="no section for 0.1.0"):
        release_notes.changelog_section(changelog, "0.1.0")


def test_changelog_section_version_is_not_a_prefix() -> None:
    """`## [0.1.0]` doesn't match `## [0.1.0.dev0]` or `## [0.1.01]`."""
    changelog = "## [0.1.0.dev0] - 2026-01-01\n\n- Entry\n## [0.1.01]\n\n- Entry\n"
    with pytest.raises(ReleaseError, match="no section"):
        release_notes.changelog_section(changelog, "0.1.0")


@pytest.mark.parametrize(
    "body",
    ["", "\n\n", "\n### Added\n\n### Fixed\n\n"],
)
def test_changelog_section_without_entries(body: str) -> None:
    changelog = f"## [0.1.0] - 2026-11-15\n{body}## [0.0.9]\n\n- Old\n"
    with pytest.raises(ReleaseError, match="no entries"):
        release_notes.changelog_section(changelog, "0.1.0")


def test_release_notes_checks_tag_first() -> None:
    with pytest.raises(ReleaseError, match="doesn't match"):
        release_notes.release_notes("v9.9.9", PYPROJECT, CHANGELOG)


def test_main_writes_notes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    output = tmp_path / "notes.md"
    code = release_notes.main(
        [
            "v0.1.0",
            "--output",
            str(output),
            "--pyproject",
            str(tmp_path / "pyproject.toml"),
            "--changelog",
            str(tmp_path / "CHANGELOG.md"),
        ]
    )
    assert code == 0
    notes = output.read_text(encoding="utf-8")
    assert notes.startswith("### Added\n")
    assert "Something not released yet" not in notes
    assert "An older entry" not in notes


def test_main_reports_error_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [Unreleased]\n\n- Entry\n", encoding="utf-8"
    )
    output = tmp_path / "notes.md"
    code = release_notes.main(
        [
            "v0.1.0",
            "--output",
            str(output),
            "--pyproject",
            str(tmp_path / "pyproject.toml"),
            "--changelog",
            str(tmp_path / "CHANGELOG.md"),
        ]
    )
    assert code == 1
    assert not output.exists()
    assert "error: CHANGELOG.md has no section for 0.1.0" in capsys.readouterr().err


def test_main_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = release_notes.main(
        [
            "v0.1.0",
            "--output",
            str(tmp_path / "notes.md"),
            "--pyproject",
            str(tmp_path / "missing.toml"),
        ]
    )
    assert code == 1
    assert "missing.toml" in capsys.readouterr().err
