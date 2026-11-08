"""Telegram Bot API notifier (free). Setup steps are in .env.example."""

from __future__ import annotations

import html

import httpx
import pandas as pd

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram hard limit is 4096 chars


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        for chunk in _chunks(text, MAX_LEN):
            r = httpx.post(
                API.format(token=self.token, method="sendMessage"),
                json={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            r.raise_for_status()


def _chunks(text: str, n: int) -> list[str]:
    out, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > n:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        out.append(cur[:n])
    return out


def _money(v) -> str:
    try:
        return "?" if pd.isna(v) else f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "?"


def _pct(v) -> str:
    try:
        return "?" if pd.isna(v) else f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "?"


def format_results(title: str, df: pd.DataFrame, top: int = 5) -> str:
    e = html.escape
    lines = [f"<b>🏡 {e(title)}</b>\n{len(df)} listings ranked. Top {min(top, len(df))}:"]
    for i, (_, r) in enumerate(df.head(top).iterrows(), 1):
        score = r.get("ai_score")
        score_txt = f"AI {int(score)}/10 · " if pd.notna(score) else ""
        beds = r.get("beds")
        baths = r.get("full_baths")
        lines.append(
            f"<b>{i}. {e(str(r.get('formatted_address', '')))}</b>\n"
            f"{_money(r.get('list_price'))} · {beds if pd.notna(beds) else '?'}bd/"
            f"{baths if pd.notna(baths) else '?'}ba · {score_txt}prescore {r.get('prescore', '?')}\n"
            f"rent≈{_money(r.get('est_rent'))} · cap {_pct(r.get('cap_rate'))} · "
            f"CF {_money(r.get('cash_flow_mo'))}/mo\n"
            + (
                f"<i>{e(str(r.get('ai_thesis')))}</i>\n"
                if isinstance(r.get("ai_thesis"), str)
                else ""
            )
            + f'<a href="{e(str(r.get("property_url", "")))}">listing</a>'
        )
    return "\n\n".join(lines)
