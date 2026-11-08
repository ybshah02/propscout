from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from propscout.config import get_settings
from propscout.models import SearchQuery, Strategy

app = typer.Typer(add_completion=False, help="PropScout — find and rank real estate opportunities.")
console = Console()


def _strategies(value: str | None) -> list[Strategy] | None:
    if not value:
        return None
    try:
        return [Strategy(v.strip().lower()) for v in value.split(",") if v.strip()]
    except ValueError as exc:
        raise typer.BadParameter("strategies must be from: str, ltr, appreciation, land") from exc


@app.command()
def search(
    prompt: str | None = typer.Option(
        None, "--prompt", "-p", help='Natural language, e.g. "3bd cabin near Asheville under 500k"'
    ),
    location: str | None = typer.Option(None, "--location", "-l", help='"City, ST", ZIP, county'),
    price_min: int | None = typer.Option(None),
    price_max: int | None = typer.Option(None),
    beds_min: int | None = typer.Option(None),
    beds_max: int | None = typer.Option(None),
    baths_min: float | None = typer.Option(None),
    sqft_min: int | None = typer.Option(None),
    sqft_max: int | None = typer.Option(None),
    lot_sqft_min: int | None = typer.Option(None),
    year_built_min: int | None = typer.Option(None),
    property_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Comma list: single_family,condos,townhomes,multi_family,land,farm,mobile",
    ),
    strategies: str | None = typer.Option(
        None, "--strategies", "-s", help="Comma list: str,ltr,appreciation,land"
    ),
    notes: str | None = typer.Option(None, "--notes", "-n", help="Soft wishes for the analyst"),
    past_days: int | None = typer.Option(None, help="Only listings from the last N days"),
    limit: int = typer.Option(200, help="Max listings to fetch"),
    analyze_top: int = typer.Option(10, "--analyze-top", "-a", help="LLM-analyse top N (0 = off)"),
    model: str | None = typer.Option(None, help="OpenRouter model id override"),
    out: Path = typer.Option(Path("results"), help="Output directory"),
    all_columns: bool = typer.Option(False, help="Include every scraped column in the CSV"),
    notify: bool = typer.Option(False, "--notify", help="Send top results to Telegram"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Search listings, underwrite them, rank them, and write CSV + Markdown."""
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING)
    from propscout import pipeline
    from propscout.export import write_outputs
    from propscout.sources import RealtorSource

    s = get_settings()
    llm = None
    if s.llm_enabled and (analyze_top > 0 or prompt):
        from propscout.agents.llm import OpenRouterLLM

        llm = OpenRouterLLM(s, model=model)
    elif analyze_top > 0:
        console.print("[yellow]OPENROUTER_API_KEY not set — skipping LLM analysis.[/]")

    if prompt:
        if llm is None:
            raise typer.BadParameter("--prompt needs OPENROUTER_API_KEY (or use structured flags)")
        from propscout.agents.parser import parse_prompt

        with console.status("Parsing prompt…"):
            query = parse_prompt(llm, prompt)
    else:
        if not location:
            raise typer.BadParameter("Provide --location or --prompt")
        query = SearchQuery(location=location)

    # Explicit flags override whatever the prompt parser produced
    overrides = {
        "location": location,
        "price_min": price_min,
        "price_max": price_max,
        "beds_min": beds_min,
        "beds_max": beds_max,
        "baths_min": baths_min,
        "sqft_min": sqft_min,
        "sqft_max": sqft_max,
        "lot_sqft_min": lot_sqft_min,
        "year_built_min": year_built_min,
        "past_days": past_days,
        "notes": notes,
        "strategies": _strategies(strategies),
        "property_types": [t.strip() for t in property_type.split(",")] if property_type else None,
    }
    query = query.model_copy(update={k: v for k, v in overrides.items() if v is not None})
    query.limit = limit
    console.print(f"[bold]Query:[/] {query.model_dump_json(exclude_none=True)}")

    with console.status("Working…") as status:
        result = pipeline.run(
            query,
            RealtorSource(proxy=s.proxy),
            s,
            llm=llm,
            analyze_top=analyze_top if llm else 0,
            on_step=lambda m: status.update(m),
        )

    for w in result.warnings:
        console.print(f"[yellow]⚠ {w}[/]")
    if result.df.empty:
        raise typer.Exit(1)

    csv_path, md_path = write_outputs(result, out, all_columns=all_columns)
    _print_table(result.df)
    console.print(f"\n[green]CSV:[/] {csv_path}\n[green]Report:[/] {md_path}")
    if llm is not None:
        u = llm.usage
        console.print(
            f"[dim]LLM tokens: {u['prompt_tokens']} in / {u['completion_tokens']} out · "
            f"cost ≈ ${u['cost']:.4f}[/]"
        )

    if notify:
        if not s.telegram_enabled:
            console.print("[yellow]TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping.[/]")
        else:
            from propscout.notify.telegram import TelegramNotifier, format_results

            TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id).send(
                format_results(f"PropScout: {query.location}", result.df)
            )
            console.print("[green]Sent to Telegram.[/]")


def _print_table(df, n: int = 10) -> None:
    t = Table(show_lines=False)
    for c in ["#", "AI", "Pre", "Address", "Price", "Bd/Ba", "Rent", "Cap", "CF/mo"]:
        t.add_column(c)

    def m(v):
        return "—" if v != v or v is None else f"${v:,.0f}"

    for _, r in df.head(n).iterrows():
        ai = r.get("ai_score")
        cap = r.get("cap_rate")
        t.add_row(
            str(r["rank"]),
            "" if ai is None or ai != ai else str(int(ai)),
            str(r.get("prescore", "")),
            str(r.get("formatted_address", ""))[:45],
            m(float(r["list_price"])),
            f"{r.get('beds')}/{r.get('full_baths')}",
            m(r.get("est_rent")),
            "—" if cap is None or cap != cap else f"{cap * 100:.1f}%",
            m(r.get("cash_flow_mo")),
        )
    console.print(t)


@app.command("notify-test")
def notify_test():
    """Send a test message to your Telegram chat."""
    s = get_settings()
    if not s.telegram_enabled:
        console.print("[red]Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env[/]")
        raise typer.Exit(1)
    from propscout.notify.telegram import TelegramNotifier

    TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id).send("✅ PropScout can reach you.")
    console.print("[green]Sent.[/]")


if __name__ == "__main__":
    app()
