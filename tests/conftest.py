from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_user_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point `TSKMNGR_CONFIG` at a missing file, so no test reads the real one.

    Tests that need a config file write it here or set the variable themselves.
    """
    path = tmp_path_factory.mktemp("config") / "config.json"
    monkeypatch.setenv("TSKMNGR_CONFIG", str(path))
    return path
