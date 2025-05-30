from argparse import ArgumentParser
from . import __version__
from .check import Check
from .verify import Verify
from .assemble import Assemble
from .create import Create
from .main import Main


class App(Main):
    """Main application class."""

    def init_argparse(self, argp: ArgumentParser) -> None:
        argp.prog = "blob_descriptor"
        argp.add_argument("--version", action="version", version=f"{__version__}")
        return super().init_argparse(argp)

    def sub_args(self) -> object:
        """Register all subcommands."""
        yield Verify(), {"name": "verify", "help": "Check files"}
        yield Check(), {"name": "check", "help": "Check chunks"}
        yield Create(), {"name": "create", "help": "Create descriptor"}
        yield Assemble(), {"name": "assemble", "help": "Assemble files"}


def main():
    """CLI entry point."""
    App().main()


if __name__ == "__main__":
    main()
