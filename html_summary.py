from __future__ import annotations

import pandas as pd
from persistence import load_previous_snapshot


def build_sparkline_svg(totals: list[float], width: int = 280, height: int = 40) -> str:
    """A minimal inline-SVG line of recent portfolio totals - no chart
    library / image hosting needed, so it renders in the HTML file and in
    most email clients that allow inline SVG."""
    values = [v for v in totals if v is not None]
    if len(values) < 2:
        return ""

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = width / (len(values) - 1)
    points = []
    for i, v in enumerate(values):
        x = i * step
        y = height - ((v - lo) / span) * (height - 8) - 4
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)

    trend_up = values[-1] >= values[0]
    color = "#16a34a" if trend_up else "#dc2626"
    last_x, last_y = points[-1].split(",")

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
        f'<circle cx="{last_x}" cy="{last_y}" r="3" fill="{color}" />'
        f"</svg>"
    )


def _format_watchlist_badge(quote: dict) -> str:
    symbol = quote.get("symbol")
    price_pence = quote.get("price_pence")
    change_pence = quote.get("change_pence")
    change_pct = quote.get("change_pct")

    change_text = ""
    if change_pence is not None:
        change_text = f" ({change_pence:+.2f}p DoD"
        if change_pct is not None:
            change_text += f", {change_pct:+.2f}%"
        change_text += ")"
    elif change_pct is not None:
        change_text = f" ({change_pct:+.2f}% DoD)"
    return f'<div class="elix">LON:{symbol}: {price_pence:.2f}p{change_text}</div>'


def build_html_summary(
    data: pd.DataFrame,
    total: float,
    today_str: str,
    previous_total: float | None = None,
    previous_by_fund: dict[str, float] | None = None,
    elix_price_pence: float | None = None,
    elix_change_pence: float | None = None,
    elix_change_pct: float | None = None,
    watchlist_quotes: list[dict] | None = None,
    failed_funds: list[str] | None = None,
    history_totals: list[float] | None = None,
    cost_basis_by_fund: dict[str, float] | None = None,
    regular_investments: list[dict] | None = None,
    plan_error: str | None = None,
) -> str:
    # Convert index to column for display
    df_display = data.reset_index().rename(columns={"index": "Fund/Share"})

    # Day-over-day comparison: use the snapshot passed in by the caller, and
    # only fall back to loading it ourselves when neither value was provided.
    if previous_total is None and previous_by_fund is None:
        previous_total, previous_by_fund = load_previous_snapshot(today_str, data.index.tolist())
    if previous_by_fund is None:
        previous_by_fund = {}

    # Attach DoD Change and DoD % to the display dataframe
    dod_changes = []
    dod_pcts = []
    for fund_name, row in data.iterrows():
        curr_val = float(row.get('Total Holding Value', 0.0))
        prev_val = previous_by_fund.get(fund_name)
        if prev_val is None:
            dod_changes.append(None)
            dod_pcts.append(None)
        else:
            chg = curr_val - prev_val
            pct = (chg / prev_val * 100.0) if prev_val else None
            dod_changes.append(chg)
            dod_pcts.append(pct)
    df_display['DoD Change'] = dod_changes
    df_display['DoD %'] = dod_pcts

    # Cost basis / unrealised P&L: only populated for funds where every
    # transaction has a known amount (see transactions.compute_positions).
    # A DoD change alone can't tell a market move from a fresh top-up; this
    # can, because it's anchored to money actually put in rather than a
    # rolling day-to-day comparison.
    total_cost_basis = 0.0
    total_with_known_basis = 0.0
    any_cost_basis = False
    if cost_basis_by_fund:
        pnl_values = []
        pnl_pcts = []
        cost_basis_values = []
        for fund_name, row in data.iterrows():
            basis = cost_basis_by_fund.get(fund_name)
            curr_val = float(row.get('Total Holding Value', 0.0))
            if basis is None:
                pnl_values.append(None)
                pnl_pcts.append(None)
                cost_basis_values.append(None)
                continue
            any_cost_basis = True
            total_cost_basis += basis
            total_with_known_basis += curr_val
            pnl = curr_val - basis
            pnl_pct = (pnl / basis * 100.0) if basis else None
            pnl_values.append(pnl)
            pnl_pcts.append(pnl_pct)
            cost_basis_values.append(basis)
        if any_cost_basis:
            df_display['Cost Basis'] = cost_basis_values
            df_display['Unrealised P&L'] = pnl_values
            df_display['Unrealised P&L %'] = pnl_pcts

    # HTML table
    # Format columns if present
    formatters = {}
    sell_preformatted = False
    if "Sell Price" in df_display.columns and "Price Currency" in df_display.columns:
        # Sell Price is in the quote's own currency (e.g. USD for US shares),
        # only Total Holding Value is converted - label it accordingly.
        symbols = {"GBP": "£", "USD": "$", "EUR": "€"}
        df_display["Sell Price"] = [
            f"{symbols.get(str(cur), str(cur) + ' ')}{float(v):,.2f}" if pd.notna(v) else ""
            for v, cur in zip(df_display["Sell Price"], df_display["Price Currency"])
        ]
        df_display = df_display.drop(columns=["Price Currency"])
        sell_preformatted = True
    if "Total Holding Value" in df_display.columns:
        formatters["Total Holding Value"] = lambda v: f"£{v:,.2f}" if pd.notna(v) else ""
    if "Sell Price" in df_display.columns and not sell_preformatted:
        formatters["Sell Price"] = lambda v: f"£{v:,.2f}" if pd.notna(v) else ""
    if "DoD Change" in df_display.columns:
        formatters["DoD Change"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"£{v:,.2f}" if v is not None else "")
    if "DoD %" in df_display.columns:
        formatters["DoD %"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"{v:.2f}%" if v is not None else "")
    if "Cost Basis" in df_display.columns:
        formatters["Cost Basis"] = lambda v: f"£{v:,.2f}" if pd.notna(v) else "—"
    if "Unrealised P&L" in df_display.columns:
        formatters["Unrealised P&L"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"£{v:,.2f}" if v is not None else "—")
    if "Unrealised P&L %" in df_display.columns:
        formatters["Unrealised P&L %"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"{v:.2f}%" if v is not None else "—")

    table_html = df_display.to_html(index=False, border=0, classes="dataframe", escape=False, formatters=formatters)

    # Build total badge safely (avoid complex f-string expressions)
    total_badge = f"Total: £{total:,.2f}"
    total_class = "total flat"
    if previous_total is not None:
        # Exclude money paid in today so the DoD move reflects performance.
        diff = total - previous_total - sum(float(b["amount_gbp"]) for b in (regular_investments or []))
        pct = None if previous_total == 0 else ((diff / previous_total) * 100.0)
        sign = "+" if diff >= 0 else ""
        pct_txt = f" ({'+' if (pct is not None and pct >= 0) else ''}{pct:.2f}%)" if pct is not None else ""
        total_badge = (
            f"Total: £{total:,.2f}  "
            f"<span style=\"margin-left:8px; padding:4px 8px; border-radius:999px;\">"
            f"{sign}£{diff:,.2f}{pct_txt}</span>"
        )
        if diff > 0:
            total_class = "total up"
        elif diff < 0:
            total_class = "total down"

    pnl_badge = ""
    if any_cost_basis and total_cost_basis:
        portfolio_pnl = total_with_known_basis - total_cost_basis
        portfolio_pnl_pct = (portfolio_pnl / total_cost_basis) * 100.0
        pnl_class = "pnl up" if portfolio_pnl >= 0 else "pnl down"
        coverage_note = "" if any_cost_basis and len(df_display) and df_display['Cost Basis'].notna().all() else " (tracked funds only)"
        pnl_badge = (
            f'<div class="{pnl_class}">Unrealised P&amp;L: {"+" if portfolio_pnl >= 0 else ""}'
            f"£{portfolio_pnl:,.2f} ({portfolio_pnl_pct:+.2f}%){coverage_note}</div>"
        )

    sparkline_html = ""
    if history_totals:
        svg = build_sparkline_svg(history_totals)
        if svg:
            sparkline_html = f'<div class="sparkline">{svg}</div>'

    watchlist_html = ""
    quotes = list(watchlist_quotes) if watchlist_quotes else []
    if not quotes and elix_price_pence is not None:
        quotes = [
            {
                "symbol": "ELIX",
                "price_pence": elix_price_pence,
                "change_pence": elix_change_pence,
                "change_pct": elix_change_pct,
            }
        ]
    if quotes:
        watchlist_html = "".join(_format_watchlist_badge(q) for q in quotes)

    warning_html = ""
    if failed_funds:
        names = ", ".join(failed_funds)
        warning_html = (
            f'<div class="warning">⚠ Could not price {len(failed_funds)} holding(s), excluded from the total: {names}</div>'
        )
    if regular_investments:
        invested = sum(float(b["amount_gbp"]) for b in regular_investments)
        parts = ", ".join(
            f"{b['label']} £{b['amount_gbp']:,.2f} ({b['units']:.4f} units, {b['month']})" for b in regular_investments
        )
        warning_html += f'<div class="warning">💷 Recorded regular investment of £{invested:,.2f}: {parts}</div>'
    if plan_error:
        warning_html += f'<div class="warning">⚠ Regular investments not applied: {plan_error}</div>'

    html=f"""
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {{ margin:0; padding:0; background:#0b1220; color:#e2e8f0; font-family:Arial,Helvetica,sans-serif; }}
        .container {{ width:100%; margin:0; background:#111827; box-shadow:0 2px 12px rgba(0,0,0,.25); overflow:hidden; border:1px solid #1f2937; }}
        .header {{ padding:16px 20px; border-bottom:1px solid #1f2937; }}
        .title {{ margin:0; font-size:20px; color:#f8fafc; }}
        .meta {{ margin-top:6px; font-size:12px; color:#94a3b8; }}
        .total {{ margin:12px 20px 0; background:#0ea5e9; color:#00131a; font-weight:800; display:inline-block; padding:8px 12px; border-radius:999px; font-size:14px; }}
        .total.up {{ background:#16a34a !important; }}
        .total.down {{ background:#dc2626 !important; }}
        .total.flat {{ background:#6b7280 !important; }}
        .content {{ padding:16px 20px 24px; }}
        .elix {{ margin:12px 20px 0; background:#1d4ed8; color:#dbeafe; font-weight:700; display:inline-block; padding:8px 12px; border-radius:999px; font-size:14px; }}
        .pnl {{ margin:12px 20px 0; font-weight:700; display:inline-block; padding:8px 12px; border-radius:999px; font-size:14px; }}
        .pnl.up {{ background:#14532d; color:#bbf7d0; }}
        .pnl.down {{ background:#7f1d1d; color:#fecaca; }}
        .warning {{ margin:12px 20px 0; background:#78350f; color:#fde68a; padding:8px 12px; border-radius:8px; font-size:12px; }}
        .sparkline {{ margin:14px 20px 0; }}

        /* Mobile-first table styles */
        table.dataframe {{
            border-collapse:collapse;
            width:100%;
            font-size:12px;
        }}
        table.dataframe th, table.dataframe td {{
            border:1px solid #374151;
            padding:8px 6px;
            text-align:left;
            color:#fff;
            word-wrap:break-word;
            max-width:120px;
        }}
        table.dataframe thead th {{
            background:#0f172a;
            color:#cbd5e1;
            border-bottom:2px solid #64748b;
            font-size:11px;
        }}
        table.dataframe tbody tr:nth-child(odd) {{ background:#0b1324; }}
        a {{ color:#7dd3fc; }}
        .footer {{ color:#64748b; font-size:11px; text-align:center; padding:12px; }}

        /* Mobile-specific improvements */
        @media (max-width: 768px) {{
            .header {{ padding:12px 16px; }}
            .title {{ font-size:18px; }}
            .meta {{ font-size:11px; }}
            .total {{
                margin:10px 16px 0;
                padding:6px 10px;
                font-size:13px;
                display:block;
                text-align:center;
            }}
            .content {{ padding:12px 16px 20px; }}
            .elix {{
                margin:10px 16px 0;
                padding:6px 10px;
                font-size:13px;
                display:block;
                text-align:center;
            }}
            .pnl {{
                margin:10px 16px 0;
                padding:6px 10px;
                font-size:13px;
                display:block;
                text-align:center;
            }}
            .warning {{
                margin:10px 16px 0;
            }}

            /* Make table scrollable horizontally on mobile */
            .table-container {{
                overflow-x:auto;
                -webkit-overflow-scrolling:touch;
                margin:0 -16px;
                padding:0 16px;
            }}

            table.dataframe {{
                font-size:11px;
                min-width:500px; /* Ensure minimum width for readability */
            }}

            table.dataframe th, table.dataframe td {{
                padding:6px 4px;
                font-size:10px;
            }}

            table.dataframe thead th {{
                font-size:10px;
            }}

            .footer {{
                font-size:10px;
                padding:10px;
            }}
        }}

        /* Extra small screens */
        @media (max-width: 480px) {{
            .header {{ padding:10px 12px; }}
            .title {{ font-size:16px; }}
            .total {{
                margin:8px 12px 0;
                padding:5px 8px;
                font-size:12px;
            }}
            .content {{ padding:10px 12px 16px; }}
            .elix {{
                margin:8px 12px 0;
                padding:5px 8px;
                font-size:12px;
            }}

            table.dataframe {{
                font-size:10px;
            }}

            table.dataframe th, table.dataframe td {{
                padding:4px 3px;
                font-size:9px;
            }}

            table.dataframe thead th {{
                font-size:9px;
            }}
        }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
        <h1 class="title">Daily Portfolio Summary</h1>
        <div class="meta">{today_str}</div>
        </div>
        <div class="{total_class}">{total_badge}</div>
        {pnl_badge}
        {watchlist_html}
        {warning_html}
        {sparkline_html}
        <div class="content">
        <div class="table-container">
        {table_html}
        </div>
        </div>
        <div class="footer">Automatic message • HL Price Update</div>
    </div>
    </body>
    </html>
    """
    return html
