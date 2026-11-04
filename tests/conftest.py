from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def user_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the home folder at an empty temporary one, for every test.

    So no test reads or writes the real `~/.tskmngr/config.json` or tasks.
    `HOME` is what `Path.home()` and `~` use on Linux and macOS,
    `USERPROFILE` on Windows.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home
