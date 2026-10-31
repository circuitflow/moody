"""Command-line interface: ``moody --help``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from moody import __version__
from moody.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from moody.streaming.history import ImportReport

app = typer.Typer(no_args_is_help=True, help="Moody: music mood analysis with modern MIR.")
models_app = typer.Typer(no_args_is_help=True, help="Manage the pretrained Essentia models.")
app.add_typer(models_app, name="models")
history_app = typer.Typer(
    no_args_is_help=True,
    help="Import listening history (Last.fm, Spotify) and see how much of it matches your library.",
)
app.add_typer(history_app, name="history")

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
    ui: Annotated[
        Path | None,
        typer.Option(
            exists=True, file_okay=False, help="Serve a built frontend (frontend/dist) at /."
        ),
    ] = None,
) -> None:
    """Run the HTTP API (and, with --ui, the web app)."""
    import os

    import uvicorn

    if ui is not None:
        if not (ui / "index.html").is_file():
            typer.echo(f"error: {ui} has no index.html; run `npm run build` in frontend/", err=True)
            raise typer.Exit(1)
        os.environ["MOODY_UI_DIR"] = str(ui.resolve())  # read by the app factory's settings
        get_settings.cache_clear()
        typer.echo(f"Moody: http://{host}:{port}")

    uvicorn.run("moody.api.app:create_app", factory=True, host=host, port=port, reload=reload)


@app.command("openapi")
def export_openapi(
    out: Annotated[Path, typer.Argument(help="Where to write the OpenAPI JSON schema.")],
) -> None:
    """Export the OpenAPI schema (used to generate the frontend client)."""
    from moody.api.app import create_app

    out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    typer.echo(f"wrote {out}")


@app.command()
def scan(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Music folder.")],
    limit: Annotated[int | None, typer.Option(help="Process at most N files.")] = None,
    workers: Annotated[int, typer.Option(min=1, help="Analysis processes.")] = 1,
    reanalyze: Annotated[
        bool, typer.Option(help="Re-analyze everything, including failures.")
    ] = False,
    fake: Annotated[
        bool, typer.Option(help="Use the fake analyzer (development; no models needed).")
    ] = False,
) -> None:
    """Index a music folder and analyze new or changed tracks."""
    from functools import partial

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TimeRemainingColumn

    from moody.analysis.analyzer import FakeAnalyzer
    from moody.jobs.scan import AnalyzerFactory, run_scan
    from moody.store import init_db, session_factory

    settings = get_settings()
    factory: AnalyzerFactory
    if fake:
        factory = FakeAnalyzer
    else:
        from moody.analysis import models
        from moody.analysis.essentia_backend import EssentiaAnalyzer

        missing = [name for name, ok in models.status(settings.models_dir).items() if not ok]
        if missing:
            typer.echo("models missing; run `moody models pull` first", err=True)
            raise typer.Exit(1)
        factory = partial(EssentiaAnalyzer, settings.models_dir)

    engine = init_db(settings.database_url)
    sessions = session_factory(engine)
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as bar:
        task = bar.add_task("analyzing", total=None)
        try:
            result = run_scan(
                path,
                sessions,
                factory,
                workers=workers,
                limit=limit,
                reanalyze=reanalyze,
                progress=lambda done, total: bar.update(task, completed=done, total=total),
            )
        finally:
            engine.dispose()
    ing = result.ingest
    typer.echo(
        f"library: {ing.added} new, {ing.moved} moved, {ing.modified} changed, "
        f"{ing.unchanged} unchanged, {ing.duplicates} identical copies skipped, "
        f"{ing.failed} unreadable"
        + (
            f"; artist/album from folder names for {ing.filled_from_folders}"
            if ing.filled_from_folders
            else ""
        )
    )
    typer.echo(f"analysis: {result.analyzed} analyzed, {result.failed} failed")
    if result.dedupe and result.dedupe.alternates:
        typer.echo(
            f"duplicates: {result.dedupe.groups} songs have extra copies; "
            f"{result.dedupe.alternates} files hidden from the catalog "
            "(`moody duplicates` lists them)"
        )
    for file, error in list(result.errors.items())[:10]:
        typer.echo(f"  failed: {file}: {error}", err=True)
    if result.cancelled:
        typer.echo("interrupted; run again to resume", err=True)
        raise typer.Exit(130)


@app.command("export-static")
def export_static_cmd(
    out: Annotated[Path, typer.Argument(help="Output folder, e.g. ../frontend/public/data")],
    k: Annotated[int, typer.Option(help="Neighbors per track.")] = 10,
) -> None:
    """Export the analyzed library as static JSON for the frontend's static mode."""
    from moody.export import export_static
    from moody.store import init_db, session_factory

    engine = init_db(get_settings().database_url)
    try:
        report = export_static(session_factory(engine), out, k=k)
    finally:
        engine.dispose()
    typer.echo(f"exported {report.tracks} tracks ({report.files} files) to {out}")


@app.command()
def duplicates() -> None:
    """List songs that exist as more than one file (e.g. WAV and MP3), and which file Moody
    uses. Files are never modified or deleted."""
    from sqlalchemy import select

    from moody.store import Track, init_db, session_factory

    engine = init_db(get_settings().database_url)
    try:
        with session_factory(engine)() as session:
            alternates = list(
                session.scalars(
                    select(Track)
                    .where(Track.duplicate_of.is_not(None))
                    .order_by(Track.duplicate_of)
                )
            )
            by_primary: dict[int, list[Track]] = {}
            for alt in alternates:
                by_primary.setdefault(alt.duplicate_of or 0, []).append(alt)
            for primary_id, alts in by_primary.items():
                primary = session.get(Track, primary_id)
                if primary is None:
                    continue
                typer.echo(f"{primary.title or '?'} — {primary.artist or 'unknown artist'}")
                typer.echo(f"  uses:  {primary.path}")
                for alt in alts:
                    typer.echo(f"  copy:  {alt.path}")
    finally:
        engine.dispose()
    if not alternates:
        typer.echo("No duplicate files found.")
    else:
        typer.echo(
            f"{len(by_primary)} songs, {len(alternates)} extra copies (hidden from the catalog)"
        )


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


def _history_summary(report: ImportReport, session: Session) -> None:
    from moody.streaming import history

    typer.echo(
        f"{report.source}: {report.new:,} new plays, {report.duplicates:,} already imported, "
        f"{report.skipped:,} skipped (under 30 s, podcasts)"
    )
    cov = history.coverage(session)
    plays = sum(c.plays for c in cov.values())
    matched = sum(c.matched for c in cov.values())
    if plays:
        typer.echo(
            f"matched to your library: {matched:,} of {plays:,} plays ({matched / plays:.0%}). "
            "Only matched plays can go on the mood map; scan more music to raise this."
        )


@history_app.command("lastfm")
def history_lastfm(
    user: Annotated[
        str | None, typer.Argument(help="Last.fm user name (default: MOODY_LASTFM_USER).")
    ] = None,
    full: Annotated[
        bool, typer.Option("--full", help="Read the whole history again, not only new scrobbles.")
    ] = False,
) -> None:
    """Import Last.fm scrobbles (needs MOODY_LASTFM_API_KEY, free at last.fm/api)."""
    import httpx2
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TimeRemainingColumn

    from moody.store import init_db, session_factory
    from moody.streaming.imports import import_lastfm
    from moody.streaming.lastfm import LastfmError

    settings = get_settings()
    name = user or settings.lastfm_user
    if not settings.lastfm_api_key or not name:
        typer.echo(
            "Set MOODY_LASTFM_API_KEY (free: https://www.last.fm/api/account/create) and pass a "
            "user name or set MOODY_LASTFM_USER.",
            err=True,
        )
        raise typer.Exit(2)
    engine = init_db(settings.database_url)
    try:
        with (
            session_factory(engine)() as session,
            httpx2.Client(timeout=30.0) as http,
            Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                MofNCompleteColumn(),
                TimeRemainingColumn(),
            ) as progress,
        ):
            task = progress.add_task("pages", total=None)
            try:
                report = import_lastfm(
                    session,
                    http,
                    settings.lastfm_api_key,
                    name,
                    full=full,
                    on_page=lambda done, total: progress.update(task, completed=done, total=total),
                )
            except LastfmError as exc:
                typer.echo(f"Last.fm: {exc}", err=True)
                raise typer.Exit(1) from exc
            progress.stop()
            _history_summary(report, session)
    finally:
        engine.dispose()


@history_app.command("spotify-export")
def history_spotify_export(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True, help="The .zip from Spotify, its folder, or one Streaming_History JSON."
        ),
    ],
) -> None:
    """Import a Spotify data download (Account > Privacy > Download your data).

    The extended streaming history has every play since the account was made; the basic one
    covers the last year."""
    from moody.store import init_db, session_factory
    from moody.streaming.imports import import_spotify_export

    engine = init_db(get_settings().database_url)
    try:
        with session_factory(engine)() as session:
            try:
                report = import_spotify_export(session, path)
            except FileNotFoundError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(1) from exc
            _history_summary(report, session)
    finally:
        engine.dispose()


@history_app.command("spotify")
def history_spotify() -> None:
    """Import your last 50 Spotify plays (connect Spotify in the web app first)."""
    import httpx2

    from moody.store import init_db, session_factory
    from moody.streaming.imports import import_spotify_recent
    from moody.streaming.spotify import SpotifyClient, SpotifyError

    settings = get_settings()
    if not settings.spotify_client_id:
        typer.echo(
            "Set MOODY_SPOTIFY_CLIENT_ID and connect Spotify in the web app first.", err=True
        )
        raise typer.Exit(2)
    engine = init_db(settings.database_url)
    try:
        with session_factory(engine)() as session, httpx2.Client(timeout=30.0) as http:
            client = SpotifyClient(session, http, settings.spotify_client_id)
            try:
                report = import_spotify_recent(session, client)
            except SpotifyError as exc:
                typer.echo(f"Spotify: {exc}", err=True)
                raise typer.Exit(1) from exc
            _history_summary(report, session)
    finally:
        engine.dispose()


@history_app.command("status")
def history_status() -> None:
    """Plays per source and how many match your library (re-matches after new scans)."""
    from moody.store import init_db, session_factory
    from moody.streaming import history

    engine = init_db(get_settings().database_url)
    try:
        with session_factory(engine)() as session:
            newly = history.rematch(session)
            cov = history.coverage(session)
    finally:
        engine.dispose()
    if not cov:
        typer.echo("No listening history yet: try `moody history lastfm <user>`.")
        return
    for source, c in sorted(cov.items()):
        span = f"{c.first:%Y-%m-%d} to {c.last:%Y-%m-%d}" if c.first and c.last else ""
        share = c.matched / c.plays if c.plays else 0
        typer.echo(
            f"{source:15} {c.plays:>8,} plays  {c.matched:>7,} matched ({share:.0%})  {span}"
        )
    if newly:
        typer.echo(f"{newly:,} more plays matched after recent scans")
