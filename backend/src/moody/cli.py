"""Command-line interface: ``moody --help``."""

import json
from pathlib import Path
from typing import Annotated

import typer

from moody import __version__

app = typer.Typer(no_args_is_help=True, help="Moody: music mood analysis with modern MIR.")


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
