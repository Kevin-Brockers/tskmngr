"""The `tskmngr` entry point. With no arguments it launches the TUI."""

from tskmngr.app import TskmngrApp


def main() -> None:
    """Run the `tskmngr` command."""
    TskmngrApp().run()
