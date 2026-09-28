"""Plotly chart builders: quarterly bars with breakdown hovers, margins, peer comparisons."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core import formatting as fmt
from core.concepts import METRICS

# Validated dark-mode categorical slots 1-3 (dataviz reference palette); gray = "peer / context"
BLUE, ORANGE, AQUA = "#3987e5", "#d95926", "#199e70"
PEER_GRAY = "#6f6e69"
GRID = "rgba(255,255,255,0.08)"
BASE_LAYOUT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   margin=dict(l=10, r=10, t=40, b=10), hoverlabel=dict(align="left", font_size=12))


def x_labels(q: pd.DataFrame) -> list[str]:
    """Two-line axis labels: fiscal quarter on top, calendar month the quarter ended below."""
    return [f"{lab}<br>{d:%b '%y}" for lab, d in zip(q["label"], q.index)]


def _scale(values) -> tuple[float, str]:
    vals = [abs(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    m = max(vals) if vals else 0
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if m >= div:
            return div, suf
    return 1.0, ""


def _sparse(fig, labels):
    step = max(1, math.ceil(len(labels) / 10))
    keep = labels[::-1][::step][::-1]  # always label the latest quarter
    fig.update_xaxes(type="category", tickmode="array", tickvals=keep, ticktext=keep, tickangle=0,
                     tickfont=dict(size=9))
    return fig


def bar_chart(q: pd.DataFrame, key: str, title: str, currency: str, derived: set, hover_extra: list[str],
              ref_line: tuple[float, str] | None = None):
    vals = pd.to_numeric(q[key], errors="coerce")
    kind = METRICS[key][1]
    labels = x_labels(q)
    der = [d in derived for d in q.index]
    main = [fmt.by_kind(v, kind, currency) for v in vals]
    ended = [f"Quarter ended {d:%b %d, %Y}" + (" · <i>Q4 derived: annual − 9-month YTD</i>" if dd else "")
             for d, dd in zip(q.index, der)]
    if kind == "money":
        div, suf = _scale(vals)
        y = vals / div
        yaxis = dict(tickprefix=fmt.symbol(currency), ticksuffix=suf,
                     tickformat=",.1f" if (y.abs().max() or 0) < 10 else ",.0f")
    elif kind == "ratio":
        y = vals
        yaxis = dict(tickformat=",.0f", ticksuffix="x")
    else:
        y = vals
        yaxis = dict(tickprefix=fmt.symbol(currency), tickformat=",.2f")
    fig = go.Figure(go.Bar(
        x=labels, y=y, marker_color=BLUE,
        marker_pattern_shape=["/" if d else "" for d in der],
        marker_pattern_fgcolor="rgba(255,255,255,0.45)",
        customdata=list(zip(main, ended, hover_extra)),
        hovertemplate="<b>%{x}</b><br><b>" + title + ": %{customdata[0]}</b><br>"
                      "<span style='font-size:11px'>%{customdata[1]}</span>%{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(title=dict(text=title, font=dict(size=15)), height=320, showlegend=False, bargap=0.25,
                      yaxis=dict(gridcolor=GRID, zeroline=True, zerolinecolor="rgba(255,255,255,0.25)", **yaxis),
                      **BASE_LAYOUT)
    if ref_line and ref_line[0] is not None:
        fig.add_hline(y=ref_line[0], line_dash="dash", line_width=1.5, line_color="rgba(255,255,255,0.7)",
                      annotation_text=ref_line[1], annotation_position="top left",
                      annotation_font=dict(size=11, color="rgba(255,255,255,0.85)"))
    return _sparse(fig, labels)


def margin_chart(q: pd.DataFrame):
    labels = x_labels(q)
    fig = go.Figure()
    for key, name, color in (("gross_margin", "Gross", BLUE), ("operating_margin", "Operating", ORANGE),
                             ("net_margin", "Net", AQUA)):
        fig.add_trace(go.Scatter(x=labels, y=q[key], name=name, mode="lines+markers",
                                 line=dict(color=color, width=2), marker=dict(size=8),
                                 hovertemplate=f"{name}: %{{y:.1%}}<extra></extra>"))
    fig.update_layout(title=dict(text="Margins", font=dict(size=15)), height=320, hovermode="x unified",
                      legend=dict(orientation="h", y=1.14, x=1, xanchor="right"),
                      yaxis=dict(gridcolor=GRID, tickformat=".0%"), **BASE_LAYOUT)
    return _sparse(fig, labels)


def peer_bar(df: pd.DataFrame, column: str, kind: str, subject: str, currency: str = "USD"):
    """Horizontal bars, one per company; the subject company in blue, peers in gray."""
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    if column in ("P/E (TTM)", "Forward P/E", "PEG"):
        s = s[s > 0]  # a negative P/E means losses, not a cheap stock
    s = s.sort_values()
    if s.empty:
        return None
    colors = [BLUE if t == subject else PEER_GRAY for t in s.index]
    text = [fmt.by_kind(v, kind, currency) for v in s]
    if kind == "money":
        div, suf = _scale(s)
        x = s / div
        xaxis = dict(tickprefix=fmt.symbol(currency), ticksuffix=suf)
    elif kind == "pct":
        x, xaxis = s, dict(tickformat=".0%")
    else:
        x, xaxis = s, dict(tickformat=",.2f")
    fig = go.Figure(go.Bar(x=x, y=list(s.index), orientation="h", marker_color=colors, text=text,
                           textposition="auto", cliponaxis=False,
                           hovertemplate="<b>%{y}</b>: %{text}<extra></extra>"))
    fig.update_layout(title=dict(text=column, font=dict(size=14)), height=60 + 34 * len(s), showlegend=False,
                      xaxis=dict(gridcolor=GRID, zeroline=True, zerolinecolor="rgba(255,255,255,0.25)", **xaxis),
                      yaxis=dict(tickfont=dict(size=12)), bargap=0.3, **BASE_LAYOUT)
    return fig


def usage_bar(counts: pd.Series, title: str):
    s = counts.sort_values()
    fig = go.Figure(go.Bar(x=s.values, y=list(s.index), orientation="h", marker_color=BLUE,
                           text=s.values, textposition="auto",
                           hovertemplate="<b>%{y}</b>: %{x} requests<extra></extra>"))
    fig.update_layout(title=dict(text=title, font=dict(size=14)), height=80 + 26 * len(s), showlegend=False,
                      xaxis=dict(gridcolor=GRID, tickformat=",d"), **BASE_LAYOUT)
    return fig


def daily_chart(daily: pd.Series):
    labels = [d.strftime("%b %d") for d in daily.index]
    fig = go.Figure(go.Bar(x=labels, y=daily.values, marker_color=BLUE,
                           hovertemplate="%{x}: %{y} requests<extra></extra>"))
    fig.update_xaxes(type="category")
    if len(labels) < 10:
        fig.update_traces(width=0.3)  # keep a few days from turning into giant slabs
    fig.update_yaxes(tickformat=",d", rangemode="tozero")
    fig.update_layout(title=dict(text="Requests per day", font=dict(size=14)), height=280, showlegend=False,
                      yaxis=dict(gridcolor=GRID), **BASE_LAYOUT)
    return fig
