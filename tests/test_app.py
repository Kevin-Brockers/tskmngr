import pytest

from tskmngr.app import TskmngrApp


@pytest.mark.asyncio
async def test_app_starts_and_quits() -> None:
    app = TskmngrApp()
    async with app.run_test() as pilot:
        assert app.title == "tskmngr"
        await pilot.press("ctrl+q")
    assert app.return_code == 0
