"""Command-line interface: ``moody --help``."""

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from moody import __version__
from moody.config import get_settings

app = typer.Typer(no_args_is_help=True, help="Moody: music mood analysis with modern MIR.")
models_app = typer.Typer(no_args_is_help=True, help="Manage the pretrained Essentia models.")
app.add_typer(models_app, name="models")

ModelsDir = Annotated[
    Path | None, typer.Option("--dir", help="Models directory (default: MOODY_MODELS_DIR).")
]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )


@app.command()
def version() -> None:
    """Print the Moody version."""
    typer.echo(__version__)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    reload: Annotated[bool, typer.Option(help="Auto-reload on code changes.")] = False,
) -> None:
    """Run the HTTP API."""
    import uvicorn

    uvicorn.run("moody.api.app:create_app", factory=True, host=host, port=port, reload=reload)


@app.command("openapi")
def export_openapi(
    out: Annotated[Path, typer.Argument(help="Where to write the OpenAPI JSON schema.")],
) -> None:
    """Export the OpenAPI schema (used to generate the frontend client)."""
    from moody.api.app import create_app

    out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    typer.echo(f"wrote {out}")


@models_app.command("pull")
def models_pull(
    models_dir: ModelsDir = None,
    update_lock: Annotated[
        bool, typer.Option(help="Record checksums in models.lock.json instead of verifying.")
    ] = False,
) -> None:
    """Download all models, verifying pinned SHA-256 checksums."""
    from moody.analysis import models

    target = models_dir or get_settings().models_dir
    try:
        models.pull(target, update_lock=update_lock)
    except models.ChecksumError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"models ready in {target}")


@models_app.command("list")
def models_list(models_dir: ModelsDir = None) -> None:
    """Show which models are present."""
    from moody.analysis import models

    for name, present in models.status(models_dir or get_settings().models_dir).items():
        typer.echo(f"{'ok     ' if present else 'missing'}  {name}")
