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
