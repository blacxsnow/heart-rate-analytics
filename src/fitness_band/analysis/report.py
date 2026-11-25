"""Reproducible analysis report for the acquisition database (read-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .baseline import baseline_report
from .circadian import cosinor, hourly_stats
from .data_loader import load_annotations, load_events, load_measurements, load_sessions
from .dynamics import dynamics_report
from .longitudinal import longitudinal_report
from .quality_control import quality_report
from .sleep_analysis import sleep_report
from .visualizations import plot_circadian, plot_longitudinal, plot_overview, plot_sleep


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def build_report(
    db_path: str | Path,
    out_dir: str | Path,
    *,
    expected_interval_s: float = 1.0,
    include_simulated: bool = False,
    plots: bool = True,
) -> dict[str, Any]:
    db = Path(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_measurements(db, include_simulated=include_simulated)
    annotations = load_annotations(db)
    sessions = load_sessions(db)
    events = load_events(db)

    quality = quality_report(df, expected_interval_s=expected_interval_s)
    baseline = baseline_report(df, annotations)
    sleep = sleep_report(df, annotations)
    hourly = hourly_stats(df)
    circadian = cosinor(hourly)
    dynamics = dynamics_report(df, annotations)
    longitudinal = longitudinal_report(df, annotations)

    _dump(out / "quality.json", quality)
    _dump(out / "baseline.json", baseline)
    _dump(out / "sleep.json", sleep)
    _dump(out / "circadian.json", {"hourly": hourly, "cosinor": circadian})
    _dump(out / "dynamics.json", dynamics)
    _dump(out / "longitudinal.json", longitudinal)
    _dump(
        out / "sessions.json",
        {
            "sessions": sessions.to_dict(orient="records") if not sessions.empty else [],
            "events": events.to_dict(orient="records") if not events.empty else [],
        },
    )

    if longitudinal.get("daily"):
        pd.DataFrame(longitudinal["daily"]).to_csv(out / "daily.csv", index=False)

    figures: dict[str, str] = {}
    if plots:
        for name, path in (
            ("overview.png", plot_overview(df, out / "overview.png")),
            ("circadian.png", plot_circadian(hourly, out / "circadian.png")),
            ("sleep.png", plot_sleep(sleep.get("trajectory", []), out / "sleep.png")),
            (
                "longitudinal.png",
                plot_longitudinal(longitudinal.get("daily", []), out / "longitudinal.png"),
            ),
        ):
            if path:
                figures[name] = str(path)

    _write_summary(out / "summary.md", quality, baseline, sleep, circadian, dynamics, longitudinal)
    return {
        "out_dir": str(out),
        "measurements": len(df),
        "annotations": len(annotations),
        "figures": figures,
    }


def _write_summary(
    path: Path,
    quality: dict,
    baseline: dict,
    sleep: dict,
    circadian: dict | None,
    dynamics: dict,
    longitudinal: dict,
) -> None:
    lines = ["# Band 9 HR analysis", ""]
    lines.append("## Data quality")
    if quality.get("available"):
        lines += [
            f"- Measurements: **{quality['total_measurements']}**",
            f"- Observed interval: **{quality['observed_sampling_interval_s']} s**",
            f"- Completeness: **{quality['completeness']}**",
            f"- Longest gap: **{quality['longest_gap_s']} s**",
            f"- Gaps > threshold: **{quality['gap_count']}**",
        ]
    else:
        lines.append("- No data.")
    lines += ["", "## Baseline"]
    overall = baseline.get("overall") if baseline.get("available") else None
    if overall:
        lines += [
            f"- Mean / median: **{overall['mean']} / {overall['median']} bpm**",
            f"- SD / MAD / IQR: **{overall['sd']} / {overall['mad']} / {overall['iqr']}**",
            f"- p5 / p95: **{overall['p05']} / {overall['p95']} bpm**",
        ]
    resting = baseline.get("observed_resting")
    if resting:
        lines.append(
            f"- Observed resting proxy: **{resting['bpm']} bpm** "
            f"({resting['method']}; {resting['confidence']})"
        )
    lines += ["", "## Sleep"]
    if sleep.get("available"):
        lines += [
            f"- Nights with data: **{sleep['nights_with_data']}**",
            f"- Sleep median: **{sleep['overall']['median']} bpm**",
            f"- Minimum sustained: **{sleep['minimum_sustained_bpm']} bpm**",
            f"- Decline vs awake resting: **{sleep['decline_from_awake_resting_bpm']} bpm**",
        ]
    else:
        lines.append(f"- {sleep.get('reason', 'unavailable')}")
    lines += ["", "## Circadian"]
    if circadian:
        lines += [
            f"- Mesor: **{circadian['mesor_bpm']} bpm**",
            f"- Amplitude: **{circadian['amplitude_bpm']} bpm**",
            f"- Acrophase: **{circadian['acrophase_hour']} h** (exploratory)",
        ]
    else:
        lines.append("- Insufficient hourly coverage for a cosinor fit.")
    lines += ["", "## Dynamics"]
    if dynamics.get("available"):
        rate = dynamics.get("rate_of_change") or {}
        lines += [
            f"- Median |Δ|: **{rate.get('median_abs_bpm_per_min')} bpm/min**",
            (
                f"- Elevated episodes: **{dynamics.get('episode_count')}** "
                f"(threshold {dynamics.get('episode_threshold_bpm')} bpm)"
            ),
        ]
        lines.append("- No RMSSD/SDNN/pNN50 is derived from 1 Hz BPM.")
    lines += ["", "## Longitudinal"]
    if longitudinal.get("available"):
        base = longitudinal.get("first_28_day_baseline") or {}
        lines += [
            f"- Days: **{longitudinal['days']}**",
            f"- First-28-day mean daily median: **{base.get('mean_daily_median_bpm')} bpm**",
            f"- Day-to-day variability: **{longitudinal.get('day_to_day_variability_bpm')} bpm**",
        ]
        lines.append("- Personal empirical baseline, not a clinical reference interval.")
    lines += [
        "",
        "## Method notes",
        "- Missing intervals are reported, never interpolated or treated as zero.",
        "- Resting HR is an observed low-activity proxy because activity data is unavailable.",
        "- Sleep intervals are manual annotations; no REM/awakening inference is made.",
        "- BPM variation is not beat-to-beat HRV; no RMSSD/SDNN/pNN50 is calculated.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    from ..paths import db_path as default_db

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db())
    parser.add_argument("--out", type=Path, default=Path("reports/analysis"))
    parser.add_argument("--expected-interval", type=float, default=1.0)
    parser.add_argument("--include-simulated", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    result = build_report(
        args.db,
        args.out,
        expected_interval_s=args.expected_interval,
        include_simulated=args.include_simulated,
        plots=not args.no_plots,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
