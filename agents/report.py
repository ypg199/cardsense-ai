"""
agents/report.py
─────────────────────────────────────────────────────────────────────────────
Downloadable PDF report of a session: the score and verdict, cashback by
category, the side-by-side card comparison, insights, and spending charts.

Drawn directly with PyMuPDF (already a dependency for reading statements),
so no browser or extra service is needed. Pure function of the session
state; the API route only streams the bytes.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz

from agents.insights import spend_insights
from agents.spend_summary import summarise_spend

PAGE_W, PAGE_H = 595, 842  # A4 in points
MARGIN = 44
CONTENT_W = PAGE_W - 2 * MARGIN
BOTTOM = PAGE_H - 50

INK = (0.07, 0.09, 0.15)
MUTED = (0.39, 0.45, 0.55)
RULE = (0.86, 0.88, 0.91)
SOFT = (0.96, 0.97, 0.98)
AMBER = (0.85, 0.47, 0.02)
GREEN = (0.09, 0.55, 0.27)
RED = (0.8, 0.15, 0.15)
SERIES = [(0.22, 0.53, 0.9), (0.85, 0.35, 0.15), (0.1, 0.62, 0.44), (0.79, 0.52, 0.0), (0.84, 0.32, 0.51)]
OTHER = (0.39, 0.45, 0.55)

# A font with the rupee sign, when the system has one; otherwise "Rs".
_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fonts() -> tuple[str | None, str | None]:
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            return regular, bold
    return None, None


def _group(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def _month(m: str, long: bool = False) -> str:
    try:
        name = _MONTHS[int(m[5:7]) - 1]
    except (ValueError, IndexError):
        return m
    return f"{name} {m[:4]}" if long else f"{name} {m[2:4]}"


def _cat(c: str) -> str:
    return c.replace("_", " ").capitalize()


class _Doc:
    """Tiny top-to-bottom layout helper with page breaks."""

    def __init__(self, footer: str):
        self.doc = fitz.open()
        self.footer = footer
        regular, bold = _fonts()
        self.rupee = "₹" if regular else "Rs "
        self._font_files = {"r": regular, "b": bold}
        self.page: fitz.Page | None = None
        self.y = 0.0
        self.new_page()

    # ── basics ────────────────────────────────────────────────────────────
    def money(self, v: float) -> str:
        sign = "-" if v < 0 else ""
        return f"{sign}{self.rupee}{_group(round(abs(v)))}"

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        for key, path in self._font_files.items():
            if path:
                self.page.insert_font(fontname=f"cs{key}", fontfile=path)
        self.y = MARGIN
        n = len(self.doc)
        self.text(MARGIN, PAGE_H - 28, self.footer, 7.5, MUTED)
        self.text(PAGE_W - MARGIN, PAGE_H - 28, f"Page {n}", 7.5, MUTED, align="right")

    def ensure(self, height: float) -> None:
        if self.y + height > BOTTOM:
            self.new_page()

    def _font(self, bold: bool) -> str:
        key = "b" if bold else "r"
        if self._font_files[key]:
            return f"cs{key}"
        return "hebo" if bold else "helv"

    def width(self, s: str, size: float, bold: bool = False) -> float:
        path = self._font_files["b" if bold else "r"]
        font = fitz.Font(fontfile=path) if path else fitz.Font("hebo" if bold else "helv")
        return font.text_length(s, fontsize=size)

    def text(self, x, y, s, size=9.5, color=INK, bold=False, align="left") -> None:
        if align == "right":
            x -= self.width(s, size, bold)
        elif align == "center":
            x -= self.width(s, size, bold) / 2
        self.page.insert_text((x, y), s, fontsize=size, fontname=self._font(bold), color=color)

    def wrap(self, s: str, size: float, max_w: float, bold: bool = False) -> list[str]:
        words, lines, line = s.split(), [], ""
        for w in words:
            trial = f"{line} {w}".strip()
            if self.width(trial, size, bold) <= max_w:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = w
        if line:
            lines.append(line)
        return lines

    def para(self, s: str, size=9.5, color=INK, bold=False, x=MARGIN, max_w=CONTENT_W, gap=4.0) -> None:
        for line in self.wrap(s, size, max_w, bold):
            self.ensure(size + 4)
            self.y += size + 2
            self.text(x, self.y, line, size, color, bold)
        self.y += gap

    def rect(self, x, y, w, h, fill, stroke=None, radius=None) -> None:
        self.page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=stroke, fill=fill, width=0.6, radius=radius)

    def line(self, x1, y1, x2, y2, color=RULE, width=0.6) -> None:
        self.page.draw_line((x1, y1), (x2, y2), color=color, width=width)

    def heading(self, s: str) -> None:
        self.ensure(60)
        self.y += 18
        self.text(MARGIN, self.y, s, 13, INK, bold=True)
        self.y += 10

    # ── blocks ────────────────────────────────────────────────────────────
    def stats(self, items: list[tuple[str, str, tuple]]) -> None:
        self.ensure(56)
        gap = 8
        w = (CONTENT_W - gap * (len(items) - 1)) / len(items)
        for i, (label, value, color) in enumerate(items):
            x = MARGIN + i * (w + gap)
            self.rect(x, self.y, w, 48, SOFT, RULE, radius=0.08)
            self.text(x + 10, self.y + 16, label.upper(), 7, MUTED)
            self.text(x + 10, self.y + 37, value, 15, color, bold=True)
        self.y += 56

    def table(self, headers: list[str], rows: list[list[str]], widths: list[float], bold_last=False) -> None:
        def draw_row(cells, bold=False, color=INK, size=8.5):
            x = MARGIN
            for i, (cell, w) in enumerate(zip(cells, widths, strict=True)):
                if i == 0:
                    self.text(x + 4, self.y, cell, size, color, bold)
                else:
                    self.text(x + w - 4, self.y, cell, size, color, bold, align="right")
                x += w

        self.ensure(30)
        self.y += 12
        draw_row(headers, bold=True, color=MUTED, size=7.5)
        self.y += 5
        self.line(MARGIN, self.y, MARGIN + CONTENT_W, self.y, RULE, 0.8)
        for n, r in enumerate(rows):
            self.ensure(16)
            self.y += 13
            last = bold_last and n == len(rows) - 1
            draw_row(r, bold=last)
            self.y += 4
            self.line(MARGIN, self.y, MARGIN + CONTENT_W, self.y)
        self.y += 4

    def bars(self, items: list[tuple[str, float, tuple]], label_w: float = 150) -> None:
        if not items:
            return
        top = max(v for _, v, _ in items) or 1
        bar_max = CONTENT_W - label_w - 70
        for label, value, color in items:
            self.ensure(16)
            self.y += 12
            self.text(MARGIN, self.y, label[:32], 8.5, INK)
            w = max(2, bar_max * value / top)
            self.rect(MARGIN + label_w, self.y - 8, w, 9, color, radius=0.2)
            self.text(MARGIN + CONTENT_W, self.y, self.money(value), 8.5, MUTED, align="right")
            self.y += 3

    def columns(self, monthly: list[dict], series: list[str]) -> None:
        """Stacked monthly columns, one colour per top category."""
        h = 150
        self.ensure(h + 40)
        top = max((m["total"] for m in monthly), default=0) or 1
        base = self.y + h
        n = len(monthly)
        slot = CONTENT_W / max(n, 1)
        bw = min(46, slot * 0.6)
        self.line(MARGIN, base, MARGIN + CONTENT_W, base, MUTED, 0.6)
        for i, m in enumerate(monthly):
            x = MARGIN + i * slot + (slot - bw) / 2
            y = base
            other = m["total"] - sum(m["by_category"].get(c, 0) for c in series)
            parts = [(m["by_category"].get(c, 0), SERIES[k]) for k, c in enumerate(series)] + [(other, OTHER)]
            for value, color in parts:
                if value <= 0:
                    continue
                ph = h * value / top
                self.rect(x, y - ph, bw, ph, color)
                y -= ph
            self.text(x + bw / 2, y - 4, self.money(m["total"]), 7, INK, align="center")
            self.text(x + bw / 2, base + 12, _month(m["month"]), 7.5, MUTED, align="center")
        self.y = base + 22
        x = MARGIN
        for k, c in enumerate([*series, "Other"]):
            color = SERIES[k] if k < len(series) else OTHER
            label = _cat(c) if c != "Other" else c
            self.rect(x, self.y - 7, 8, 8, color, radius=0.2)
            self.text(x + 12, self.y, label, 7.5, MUTED)
            x += 20 + self.width(label, 7.5)
        self.y += 6

    def save(self) -> bytes:
        return self.doc.tobytes(garbage=3, deflate=True)


def build_report(state: dict[str, Any]) -> bytes:
    """Render the session as a PDF and return its bytes."""
    cards = state.get("cards") or []
    summary = summarise_spend(cards)
    insights = spend_insights(cards, summary)
    months = [m for m in summary["months"] if m != "unknown"]
    period = f"{_month(months[0], True)} to {_month(months[-1], True)}" if months else "No dated spending"
    generated = datetime.now(UTC).strftime("%d %b %Y")
    sample = bool(state.get("sample"))

    d = _Doc(footer=f"CardSense AI report, generated {generated}" + (" from sample data" if sample else ""))

    # ── Title ────────────────────────────────────────────────────────────
    d.y += 6
    d.text(MARGIN, d.y, "CARDSENSE AI", 8.5, AMBER, bold=True)
    d.y += 26
    title = "Spending report" if state.get("mode") == "spend" else "Credit card report"
    d.text(MARGIN, d.y, title, 22, INK, bold=True)
    d.y += 18
    names = ", ".join(c.get("card_name", "") for c in cards if c.get("card_name"))
    d.text(MARGIN, d.y, f"{names}  |  {period}", 9.5, MUTED)
    if sample:
        d.y += 14
        d.text(MARGIN, d.y, "Made with the built-in sample statements. No real financial data.", 8.5, AMBER)
    d.y += 8

    comp = state.get("comparison_result") or {}
    n_months = max(len(months), 1)

    # ── Verdict and score ────────────────────────────────────────────────
    if comp:
        d.ensure(90)
        d.y += 14
        d.rect(MARGIN, d.y, CONTENT_W, 78, SOFT, RULE, radius=0.06)
        score = int(comp.get("card_score", 0))
        color = GREEN if score >= 70 else AMBER if score >= 40 else RED
        d.text(MARGIN + 46, d.y + 46, str(score), 30, color, bold=True, align="center")
        d.text(MARGIN + 46, d.y + 62, "out of 100", 7, MUTED, align="center")
        top = d.y
        d.y += 8
        d.para(comp.get("verdict", ""), 13, INK, bold=True, x=MARGIN + 96, max_w=CONTENT_W - 110, gap=2)
        d.para(comp.get("verdict_reason", ""), 9, MUTED, x=MARGIN + 96, max_w=CONTENT_W - 110)
        d.y = max(d.y, top + 78)

    # ── Headline numbers ─────────────────────────────────────────────────
    earned = sum(sum((c.get("cashback_result") or {}).get("earned_breakdown", {}).values()) for c in cards)
    missed = sum(sum((c.get("cashback_result") or {}).get("missed_breakdown", {}).values()) for c in cards)
    d.y += 12
    stats = [("Spend per month", d.money(summary["total_spend"] / n_months), INK)]
    if comp:
        stats += [
            ("Cashback per month", d.money(earned / n_months), GREEN),
            ("Missed per month", d.money(missed / n_months), RED if missed else MUTED),
        ]
    stats.append(("Purchases", str(summary["transactions"]), INK))
    d.stats(stats)

    # ── Insights ─────────────────────────────────────────────────────────
    if insights:
        d.heading("What stands out")
        for i in insights:
            d.ensure(30)
            d.y += 4
            d.rect(MARGIN, d.y + 3, 3, 22, AMBER)
            d.para(i["title"], 9.5, INK, bold=True, x=MARGIN + 10, max_w=CONTENT_W - 10, gap=0)
            d.para(i["detail"], 8.5, MUTED, x=MARGIN + 10, max_w=CONTENT_W - 10, gap=2)

    # ── Card comparison ──────────────────────────────────────────────────
    table = comp.get("comparison") or {}
    columns = table.get("cards") or []
    if len(columns) > 1:
        d.heading("Your card vs the alternatives")
        d.para("Cashback per month on your actual average month of spending.", 8.5, MUTED, gap=0)
        cats = [r["category"] for r in table.get("categories", [])][:6]
        label_w = 120
        col_w = (CONTENT_W - label_w) / len(columns)
        headers = [""] + [
            (c["card_name"].replace(" Credit Card", "") + (" *" if c["is_current"] else ""))[:22]
            for c in columns
        ]
        rows = [[_cat(cat)] + [d.money(c["by_category"].get(cat, 0)) for c in columns] for cat in cats]
        rows.append(["Total per month"] + [d.money(c["monthly_cashback"]) for c in columns])
        rows.append(
            ["Annual fee"] + [d.money(-c["annual_fee"]) if c["annual_fee"] else "Free" for c in columns]
        )
        rows.append(["Net per year"] + [d.money(c["net_annual"]) for c in columns])
        d.table(headers, rows, [label_w] + [col_w] * len(columns), bold_last=True)
        d.para("* your card, as you use it today. The others assume their offers are used fully.", 7.5, MUTED)

    recs = comp.get("recommendations") or []
    if recs:
        d.heading("Recommended cards")
        for n, r in enumerate(recs, 1):
            d.ensure(40)
            gain = r.get("improvement_over_current_monthly", 0)
            d.para(f"{n}. {r['card_name']}  (+{d.money(gain)} a month)", 10, INK, bold=True, gap=0)
            if r.get("why_better"):
                d.para(r["why_better"], 8.5, MUTED, x=MARGIN + 12, max_w=CONTENT_W - 12, gap=0)
            if r.get("caveat"):
                d.para(r["caveat"], 8, MUTED, x=MARGIN + 12, max_w=CONTENT_W - 12, gap=2)
            d.y += 4

    # ── Cashback by category ─────────────────────────────────────────────
    for card in cards:
        cr = card.get("cashback_result")
        if not cr:
            continue
        d.heading(f"Cashback by category: {card.get('card_name', '')}")
        cats = sorted(
            set(cr.get("earned_breakdown", {})) | set(cr.get("missed_breakdown", {})),
            key=lambda c: -(cr["earned_breakdown"].get(c, 0) + cr["missed_breakdown"].get(c, 0)),
        )
        rows = []
        for c in cats:
            e, m = cr["earned_breakdown"].get(c, 0), cr["missed_breakdown"].get(c, 0)
            pct = round(e / (e + m) * 100) if e + m else 0
            rows.append([_cat(c), d.money(e), d.money(m) if m else "-", f"{pct}%"])
        te, tm = sum(cr["earned_breakdown"].values()), sum(cr["missed_breakdown"].values())
        rows.append(["Total for the period", d.money(te), d.money(tm), f"{cr.get('utilization_score', 0)}%"])
        d.table(["Category", "Earned", "Missed", "Used"], rows, [CONTENT_W - 270, 90, 90, 90], bold_last=True)

    # ── Spending ─────────────────────────────────────────────────────────
    if summary["monthly"]:
        d.heading("Spending per month")
        series = [c["category"] for c in summary["categories"][:5]]
        d.columns([m for m in summary["monthly"] if m["month"] != "unknown"], series)

        d.heading("Where the money went")
        top_cats = summary["categories"][:8]
        d.bars(
            [(_cat(c["category"]), c["total"], SERIES[i] if i < 5 else OTHER) for i, c in enumerate(top_cats)]
        )

        d.heading("Top merchants")
        d.bars([(m["merchant"], m["total"], OTHER) for m in summary["merchants"][:8]], label_w=180)

    tips = comp.get("tips") or []
    if tips:
        d.heading("Tips")
        for t in tips:
            d.para(f"- {t}", 9, INK, gap=2)

    return d.save()
