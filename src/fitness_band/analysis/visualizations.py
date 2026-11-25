"""Matplotlib figures for the analysis application (headless-safe)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def plot_overview(df: pd.DataFrame, out: Path) -> Path | None:
    if df.empty:
        return None
    plt = _plt()
    series = df.set_index("timestamp_local")["heart_rate_bpm"].sort_index()
    if len(series) > 5000:
        series = series.resample("1min").median().dropna()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(series.index, series.values, linewidth=0.8, color="#d95f3b")
    ax.set_ylabel("HR (bpm)")
    ax.set_title("Heart rate — full record")
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_circadian(hourly: list[dict[str, Any]], out: Path) -> Path | None:
    if not hourly:
        return None
    plt = _plt()
    hours = [row["hour"] for row in hourly]
    median = [row["median"] for row in hourly]
    p05 = [row["p05"] for row in hourly]
    p95 = [row["p95"] for row in hourly]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hours, median, marker="o", color="#d95f3b", label="hourly median")
    ax.fill_between(hours, p05, p95, color="#d95f3b", alpha=0.18, label="p5–p95")
    ax.set_xlabel("Local hour")
    ax.set_ylabel("HR (bpm)")
    ax.set_xticks(range(0, 24, 2))
    ax.set_title("Circadian HR summary")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_sleep(trajectory: list[dict[str, Any]], out: Path) -> Path | None:
    if not trajectory:
        return None
    plt = _plt()
    minutes = [row["minute"] for row in trajectory]
    values = [row["median_bpm"] for row in trajectory]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(minutes, values, color="#5b6ee1")
    ax.set_xlabel("Minutes from annotated bedtime")
    ax.set_ylabel("Median HR (bpm)")
    ax.set_title("Sleep HR trajectory (manual annotations)")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out


def plot_longitudinal(daily: list[dict[str, Any]], out: Path) -> Path | None:
    if not daily:
        return None
    plt = _plt()
    frame = pd.DataFrame(daily)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(
        frame.index,
        frame["median"],
        marker="o",
        markersize=2,
        color="#d95f3b",
        label="daily median",
    )
    if "rolling_7d_median" in frame:
        ax.plot(frame.index, frame["rolling_7d_median"], color="#2a9d8f", label="7-day median")
    if "ewma_7d" in frame:
        ax.plot(
            frame.index, frame["ewma_7d"], color="#e9c46a", linestyle="--", label="EWMA (7-day)"
        )
    ax.set_ylabel("HR (bpm)")
    ax.set_title("Longitudinal daily HR")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)
    return out
