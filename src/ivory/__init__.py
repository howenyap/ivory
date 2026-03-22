"""Bootstrap package for the Ivory project."""

__all__ = ["__version__", "main"]

__version__ = "0.1.0"


def main() -> int:
    from ivory.cli import main as cli_main

    return cli_main()
