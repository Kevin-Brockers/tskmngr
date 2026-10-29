import pytest

from tskmngr import cli
from tskmngr.app import TskmngrApp


def test_main_runs_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[TskmngrApp] = []
    monkeypatch.setattr(TskmngrApp, "run", lambda self: started.append(self))

    cli.main()

    assert len(started) == 1
