import pytest
from textual.app import App
from textual.widgets import Button

from tskmngr.widgets.confirm_discard import ConfirmDiscardScreen


class DialogApp(App[None]):
    """Shows the dialog and keeps its answer."""

    def __init__(self) -> None:
        super().__init__()
        self.answers: list[bool | None] = []

    def on_mount(self) -> None:
        self.push_screen(ConfirmDiscardScreen(), self.answers.append)


def test_bindings_have_stable_ids() -> None:
    ids = {binding.id for binding in ConfirmDiscardScreen.BINDINGS}

    assert ids == {"confirm_discard.yes", "confirm_discard.no"}


@pytest.mark.asyncio
async def test_no_has_the_focus() -> None:
    app = DialogApp()
    async with app.run_test():
        assert app.screen.query_one("#no", Button).has_focus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keys", "answer"),
    [
        (["y"], True),
        (["n"], False),
        (["escape"], False),
        (["enter"], False),
        (["tab", "enter"], True),
    ],
)
async def test_answers(keys: list[str], answer: bool) -> None:
    app = DialogApp()
    async with app.run_test() as pilot:
        await pilot.press(*keys)

        assert app.answers == [answer]
