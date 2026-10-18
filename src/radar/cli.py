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


def _sweep_dir(config, sweep: str) -> Path:
    from .diff import previous_sweep
    from .sweep import sweeps_dir

    root = sweeps_dir(config)
    path = previous_sweep(root, "") if sweep == "latest" else root / sweep
    if path is None or not (path / "manifest.json").exists():
        raise typer.BadParameter(f"no sweep {sweep!r} in {root}")
    return path


@app.command()
def detect(sweep: str = typer.Option("latest", help="latest or a sweep id"), config: Path = CONFIG):
    """Run all detectors, levels and cutoffs; write derived/ outputs and brief.md."""
    from .brief import write_brief
    from .detectors import run_detect

    cfg = load_config(config)
    path = _sweep_dir(cfg, sweep)
    summary = run_detect(path, cfg)
    brief = write_brief(path, cfg)
    typer.echo(f"{summary['n_signals']} signals, {summary['n_assessments']} assessments "
               f"in {summary['seconds']} s -> {brief}")


@app.command()
def brief(sweep: str = typer.Option("latest", help="latest or a sweep id"), config: Path = CONFIG):
    """Rewrite derived/brief.md from the detect outputs."""
    from .brief import write_brief

    cfg = load_config(config)
    typer.echo(str(write_brief(_sweep_dir(cfg, sweep), cfg)))


@app.command()
def embed(sweep: str = typer.Option("latest", help="latest or a sweep id"), config: Path = CONFIG):
    """Embed title + abstract with Albert (cached: only new texts are sent)."""
    from .semantic.embed import run_embed

    cfg = load_config(config)
    meta = run_embed(_sweep_dir(cfg, sweep), cfg)
    typer.echo(f"{meta['mapped']} works embedded with {meta['model_id']}: {meta['embedded_now']} new, "
               f"{meta['from_cache']} from cache, {meta['tokens']:,} tokens, cost {meta['cost']} "
               f"in {meta['seconds']} s")


@app.command("map")
def map_(sweep: str = typer.Option("latest", help="latest or a sweep id"), config: Path = CONFIG):
    """Clusters, 2-D and 3-D map coordinates, regions and cluster trends (offline, CPU-heavy)."""
    from .semantic.landscape import run_map

    cfg = load_config(config)
    meta = run_map(_sweep_dir(cfg, sweep), cfg)
    typer.echo(f"{meta['points']} points, {meta['clusters']} clusters, {meta['regions']} regions; "
               f"outliers {meta['outlier_share_before']:.1%} -> {meta['outlier_share_after']:.1%}; "
               f"largest cluster {meta['largest_cluster_share']:.1%}; "
               f"median top-1 topic share {meta['median_top1_topic_share']} in {meta['seconds']} s")
    for warning in meta["warnings"]:
        typer.echo(f"warning: {warning}")


if __name__ == "__main__":
    app()
