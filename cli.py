#!/usr/bin/env python3
"""Swyft CLI — Intelligent P2P Network Analyzer & Optimizer"""

import asyncio
import sys
from pathlib import Path

import click
import yaml
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------ #
# CLI group                                                            #
# ------------------------------------------------------------------ #

@click.group()
@click.option("--config", default="config.yaml", help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx, config: str, verbose: bool):
    """Swyft — Intelligent P2P Network Analyzer & Optimizer"""
    ctx.ensure_object(dict)
    try:
        ctx.obj["config"] = load_config(config)
    except FileNotFoundError:
        console.print(f"[red]Config not found: {config}[/red]")
        sys.exit(1)

    log_level = "DEBUG" if verbose else ctx.obj["config"].get("logging", {}).get("level", "INFO")
    logger.remove()
    logger.add(sys.stderr, level=log_level, format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    log_file = ctx.obj["config"].get("logging", {}).get("file", "logs/swyft.log")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logger.add(log_file, rotation="50 MB", retention="7 days", level="DEBUG")


# ------------------------------------------------------------------ #
# download                                                             #
# ------------------------------------------------------------------ #

@main.command()
@click.argument("torrent_file", type=click.Path(exists=True))
@click.option("--output", "-o", default="./downloads", help="Output directory")
@click.pass_context
def download(ctx, torrent_file: str, output: str):
    """Download a torrent with ML-optimised peer selection."""
    from swyft.core.torrent_engine import TorrentEngine

    config = ctx.obj["config"]
    engine = TorrentEngine(config)

    try:
        metadata = engine.parse_torrent_file(Path(torrent_file))
    except Exception as e:
        console.print(f"[red]Failed to parse torrent: {e}[/red]")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]{metadata.name}[/bold cyan]\n"
            f"Size: [green]{metadata.total_size / 1e9:.2f} GB[/green]  "
            f"Pieces: [yellow]{len(metadata.pieces)}[/yellow]  "
            f"Tracker: [dim]{metadata.tracker_url}[/dim]",
            title="[bold]Swyft Download[/bold]",
        )
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>5.1f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )
    task_id = progress.add_task("Downloading…", total=metadata.total_size)

    async def run():
        async def update_progress():
            while engine.running:
                status = engine.get_status()
                progress.update(
                    task_id,
                    completed=status["bytes_downloaded"],
                    description=f"Peers: {status['peers_active']}/{status['peers_total']} | "
                                f"Speed: {status['download_speed_bps'] / 1e6:.2f} MB/s",
                )
                await asyncio.sleep(0.5)

        with progress:
            asyncio.create_task(update_progress())
            await engine.start(Path(torrent_file), Path(output))

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Download interrupted[/yellow]")
        asyncio.run(engine.stop())


# ------------------------------------------------------------------ #
# analyze                                                              #
# ------------------------------------------------------------------ #

@main.command()
@click.argument("torrent_file", type=click.Path(exists=True))
@click.pass_context
def analyze(ctx, torrent_file: str):
    """Parse a .torrent file and display swarm analytics without downloading."""
    from swyft.core.torrent_engine import TorrentEngine
    from swyft.core.tracker import TrackerClient

    config = ctx.obj["config"]
    engine = TorrentEngine(config)
    metadata = engine.parse_torrent_file(Path(torrent_file))

    table = Table(title=f"Torrent Info: {metadata.name}", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Info Hash", metadata.info_hash.hex())
    table.add_row("Name", metadata.name)
    table.add_row("Total Size", f"{metadata.total_size / 1e9:.4f} GB")
    table.add_row("Piece Length", f"{metadata.piece_length // 1024} KB")
    table.add_row("Piece Count", str(len(metadata.pieces)))
    table.add_row("Files", str(len(metadata.files)))
    table.add_row("Private", str(metadata.private))
    table.add_row("Tracker", metadata.tracker_url)
    table.add_row("Alt Trackers", str(len(metadata.announce_list)))

    console.print(table)

    async def scrape():
        tracker = TrackerClient(config)
        console.print("\n[dim]Scraping tracker...[/dim]")
        result = await tracker.scrape(metadata.tracker_url, metadata.info_hash)
        if result:
            st = Table(title="Swarm Stats", show_header=True, header_style="bold yellow")
            st.add_column("Metric")
            st.add_column("Count", justify="right")
            st.add_row("[green]Seeders[/green]", str(result["complete"]))
            st.add_row("[red]Leechers[/red]", str(result["incomplete"]))
            st.add_row("Times downloaded", str(result["downloaded"]))
            console.print(st)
        else:
            console.print("[dim]Scrape unavailable for this tracker[/dim]")

    asyncio.run(scrape())


# ------------------------------------------------------------------ #
# serve (API + dashboard backend)                                      #
# ------------------------------------------------------------------ #

@main.command()
@click.option("--host", default=None, help="Bind host (overrides config)")
@click.option("--port", "-p", default=None, type=int, help="Bind port (overrides config)")
@click.pass_context
def serve(ctx, host: str, port: int):
    """Start the Swyft REST API and WebSocket server."""
    import uvicorn
    from swyft.api.server import create_app

    config = ctx.obj["config"]
    h = host or config.get("api", {}).get("host", "0.0.0.0")
    p = port or config.get("api", {}).get("port", 8000)

    app = create_app(config)
    console.print(f"[bold green]Swyft API[/bold green] running on http://{h}:{p}")
    console.print(f"  Docs:      http://{h}:{p}/docs")
    console.print(f"  WebSocket: ws://{h}:{p}/ws")

    uvicorn.run(app, host=h, port=p, log_level="warning")


# ------------------------------------------------------------------ #
# status                                                               #
# ------------------------------------------------------------------ #

@main.command()
@click.option("--api-url", default="http://localhost:8000", help="Swyft API URL")
def status(api_url: str):
    """Query a running Swyft instance for download status."""
    import urllib.request
    import json

    try:
        with urllib.request.urlopen(f"{api_url}/torrent/status", timeout=3) as r:
            data = json.loads(r.read())
    except Exception as e:
        console.print(f"[red]Cannot reach API: {e}[/red]")
        return

    if data.get("status") == "idle":
        console.print("[dim]No active download[/dim]")
        return

    table = Table(title="Download Status", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    progress_pct = data.get("progress", 0) * 100
    speed_mbps = data.get("download_speed_bps", 0) / 1e6
    eta = data.get("eta_seconds", float("inf"))

    table.add_row("Name", data.get("name", "?"))
    table.add_row("Progress", f"{progress_pct:.1f}%")
    table.add_row("Speed", f"{speed_mbps:.2f} MB/s")
    table.add_row("ETA", f"{int(eta)}s" if eta != float("inf") else "∞")
    table.add_row("Peers", f"{data.get('peers_active', 0)} / {data.get('peers_total', 0)}")
    table.add_row("Connections", str(data.get("connections", 0)))

    console.print(table)


if __name__ == "__main__":
    main()
