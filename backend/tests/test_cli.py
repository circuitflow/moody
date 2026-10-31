import json
from pathlib import Path

from typer.testing import CliRunner

from moody import __version__
from moody.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_openapi_export(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    result = runner.invoke(app, ["openapi", str(out)])
    assert result.exit_code == 0
    assert json.loads(out.read_text())["info"]["title"] == "Moody"


def test_serve_ui_requires_a_build(tmp_path: Path) -> None:
    empty = tmp_path / "dist"
    empty.mkdir()
    result = runner.invoke(app, ["serve", "--ui", str(empty)])
    assert result.exit_code == 1
    assert "no index.html" in result.output
