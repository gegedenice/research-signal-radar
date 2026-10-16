"""The `radar` command."""

import logging
from pathlib import Path

import typer

from .config import load_config, load_env

app = typer.Typer(no_args_is_help=True, add_completion=False)

CONFIG = typer.Option(Path("config/ird.toml"), "--config", "-c", help="Universe and parameters (TOML)")


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_env()


@app.command()
def sweep(config: Path = CONFIG):
    """Harvest the universe into data/sweeps/<sweep_id>/ (and diff against the previous sweep)."""
    from .sweep import run_sweep

    path = run_sweep(load_config(config))
    typer.echo(str(path))


@app.command()
def diff(old: str, new: str, config: Path = CONFIG):
    """Write data/sweeps/<new>/diff.json comparing two stored sweeps."""
    from .diff import diff_sweeps
    from .sweep import sweeps_dir, write_json

    root = sweeps_dir(load_config(config))
    target = root / new / "diff.json"
    write_json(target, diff_sweeps(root / old, root / new))
    typer.echo(str(target))


if __name__ == "__main__":
    app()
