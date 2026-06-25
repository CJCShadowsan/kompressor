from importlib.metadata import version

import typer

import kompressor
from kompressor.cli import app


def test_package_exposes_version() -> None:
    assert kompressor.__version__ == version("kompressor")


def test_cli_app_is_typer_application() -> None:
    assert isinstance(app, typer.Typer)
