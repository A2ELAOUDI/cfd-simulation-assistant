"""Convergence analysis for OpenFOAM and ANSYS Fluent simulation logs.

Detects: divergence, oscillations, plateaus.
Provides actionable fix suggestions mapped to detected issue types.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for CI/server environments
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenFOAM log parser
# ---------------------------------------------------------------------------

# Patterns for OpenFOAM residual lines
_SOLVER_RE = re.compile(
    r"(?:smoothSolver|PCG|PBiCG|GAMG|BiCGStab|diagonal):\s+"
    r"Solving for (\w+),\s+"
    r"Initial residual = ([\d.eE+\-]+),\s+"
    r"Final residual = ([\d.eE+\-]+),\s+"
    r"No Iterations (\d+)"
)
_TIME_RE = re.compile(r"^Time\s*=\s*([\d.eE+\-]+)", re.MULTILINE)
_EXEC_TIME_RE = re.compile(r"ExecutionTime\s*=\s*([\d.]+)\s*s")
_CONTINUITY_RE = re.compile(
    r"time step continuity errors\s*:.*global\s*=\s*([\d.eE+\-]+)"
)
_COURANT_RE = re.compile(r"Courant Number mean:\s*([\d.eE+\-]+)\s+max:\s*([\d.eE+\-]+)")


def load_openfoam_log(path: str | Path) -> pd.DataFrame:
    """Parse an OpenFOAM solver log file into a tidy DataFrame.

    Each row corresponds to one (time_step, field) pair.

    Returns
    -------
    DataFrame with columns:
    ['time', 'field', 'initial_residual', 'final_residual',
     'n_iterations', 'continuity_error', 'courant_max', 'exec_time_s']

    Empty DataFrame if the file cannot be parsed.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read log %s: %s", path, exc)
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    current_time: float | None = None
    current_courant_max: float | None = None
    current_continuity: float | None = None
    current_exec_time: float | None = None

    for line in text.splitlines():
        # Time step header
        t_m = _TIME_RE.match(line)
        if t_m:
            current_time = float(t_m.group(1))
            current_continuity = None
            current_courant_max = None
            continue

        # Courant number
        co_m = _COURANT_RE.search(line)
        if co_m:
            current_courant_max = float(co_m.group(2))
            continue

        # Continuity error
        cont_m = _CONTINUITY_RE.search(line)
        if cont_m:
            current_continuity = float(cont_m.group(1))
            continue

        # Execution time
        exec_m = _EXEC_TIME_RE.search(line)
        if exec_m:
            current_exec_time = float(exec_m.group(1))
            continue

        # Residual line
        sol_m = _SOLVER_RE.search(line)
        if sol_m and current_time is not None:
            rows.append(
                {
                    "time": current_time,
                    "field": sol_m.group(1),
                    "initial_residual": float(sol_m.group(2)),
                    "final_residual": float(sol_m.group(3)),
                    "n_iterations": int(sol_m.group(4)),
                    "continuity_error": current_continuity,
                    "courant_max": current_courant_max,
                    "exec_time_s": current_exec_time,
                }
            )

    if not rows:
        log.warning("No residual data found in %s", path)
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["time", "field"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Issue detectors
# ---------------------------------------------------------------------------

def _as_long_residuals(residuals_df: pd.DataFrame) -> pd.DataFrame:
    """Return residual data in the OpenFOAM-style long format used by detectors."""
    if residuals_df.empty or {"field", "initial_residual"}.issubset(residuals_df.columns):
        return residuals_df

    x_col = "time" if "time" in residuals_df.columns else "iter" if "iter" in residuals_df.columns else residuals_df.columns[0]
    value_cols = [
        c for c in residuals_df.select_dtypes(include="number").columns
        if c != x_col
    ]
    if not value_cols:
        return pd.DataFrame()

    long_df = residuals_df.melt(
        id_vars=[x_col],
        value_vars=value_cols,
        var_name="field",
        value_name="initial_residual",
    )
    if x_col != "time":
        long_df = long_df.rename(columns={x_col: "time"})
    long_df["final_residual"] = long_df["initial_residual"]
    long_df["n_iterations"] = 1
    return long_df.sort_values(["time", "field"]).reset_index(drop=True)


def detect_divergence(
    residuals_df: pd.DataFrame,
    threshold_jump: float = 10.0,
    nan_check: bool = True,
) -> tuple[bool, str]:
    """Detect divergence in a residuals DataFrame.

    Parameters
    ----------
    threshold_jump:
        Flag if any residual increases by more than this factor in one step.
    nan_check:
        Also flag NaN/Inf residuals as divergence.

    Returns
    -------
    (is_diverged, explanation)
    """
    if residuals_df.empty:
        return False, "No data to analyse."

    residuals_df = _as_long_residuals(residuals_df)
    if residuals_df.empty:
        return False, "No residual columns found."

    col = "initial_residual"
    if col not in residuals_df.columns:
        return False, "Column 'initial_residual' not found."

    series = residuals_df[col]

    if nan_check and series.isin([np.inf, -np.inf]).any():
        return True, "Infinite residual detected — solver has diverged (NaN/Inf cascade)."
    if nan_check and series.isna().any():
        return True, "NaN residual detected — solver has diverged."

    # Detect sudden large jumps per field
    for field, grp in residuals_df.groupby("field"):
        vals = grp[col].values
        if len(vals) < 2:
            continue
        ratios = np.where(vals[:-1] > 1e-15, vals[1:] / vals[:-1], 0)
        if (ratios > threshold_jump).any():
            worst_idx = int(np.argmax(ratios))
            worst_time = grp["time"].iloc[worst_idx + 1]
            return (
                True,
                f"Divergence detected in field `{field}` at t={worst_time:.4f} s "
                f"(residual increased by factor {ratios[worst_idx]:.1f}).",
            )

    return False, "No divergence detected."


def detect_oscillations(
    residuals_df: pd.DataFrame,
    field: str | None = None,
    min_cycles: int = 3,
    amplitude_ratio: float = 5.0,
) -> tuple[bool, str]:
    """Detect oscillating (non-monotone) residuals.

    Parameters
    ----------
    field:
        Specific field to analyse. If None, analyse all fields.
    min_cycles:
        Minimum number of direction-reversals to flag.
    amplitude_ratio:
        Ratio of local max to local min to count as oscillation.

    Returns
    -------
    (is_oscillating, explanation)
    """
    if residuals_df.empty:
        return False, "No data to analyse."

    residuals_df = _as_long_residuals(residuals_df)
    if residuals_df.empty:
        return False, "No residual columns found."

    col = "initial_residual"
    fields_to_check = (
        [field]
        if field
        else residuals_df["field"].unique().tolist()
    )

    for f in fields_to_check:
        grp = residuals_df[residuals_df["field"] == f]
        if len(grp) < 6:
            continue
        vals = np.log10(grp[col].values + 1e-20)
        # Count sign changes in the first derivative
        diff = np.diff(vals)
        sign_changes = np.sum(np.diff(np.sign(diff)) != 0)
        # Check amplitude of oscillation
        rolling_max = pd.Series(vals).rolling(5).max()
        rolling_min = pd.Series(vals).rolling(5).min()
        amplitude = 10 ** (rolling_max - rolling_min)
        if sign_changes >= min_cycles and (amplitude > amplitude_ratio).any():
            return (
                True,
                f"Oscillations detected in `{f}` residual "
                f"({sign_changes} direction reversals, "
                f"max amplitude ratio ≈ {amplitude.max():.1f}×).",
            )

    return False, "No significant oscillations detected."


def detect_plateaus(
    residuals_df: pd.DataFrame,
    field: str | None = None,
    window: int = 10,
    improvement_threshold: float = 0.05,
    target_tolerance: float = 1e-4,
) -> tuple[bool, str]:
    """Detect stalled convergence (plateau) in residuals.

    A plateau is flagged when the residual has not decreased by more than
    `improvement_threshold` (fractional change) over `window` steps AND
    is still above `target_tolerance`.

    Returns
    -------
    (is_plateaued, explanation)
    """
    if residuals_df.empty:
        return False, "No data to analyse."

    residuals_df = _as_long_residuals(residuals_df)
    if residuals_df.empty:
        return False, "No residual columns found."

    col = "initial_residual"
    fields_to_check = (
        [field]
        if field
        else residuals_df["field"].unique().tolist()
    )

    plateaued_fields: list[str] = []
    for f in fields_to_check:
        grp = residuals_df[residuals_df["field"] == f]
        if len(grp) < window:
            continue
        vals = grp[col].values
        last_window = vals[-window:]
        fractional_change = (last_window.max() - last_window.min()) / (last_window.max() + 1e-20)
        final_val = last_window[-1]

        if fractional_change < improvement_threshold and final_val >= target_tolerance:
            plateaued_fields.append(
                f"`{f}` (plateau at {final_val:.2e}, Δ={fractional_change:.1%})"
            )

    if plateaued_fields:
        return (
            True,
            f"Convergence plateau detected in: {', '.join(plateaued_fields)}. "
            f"Residuals have not improved over the last {window} time steps.",
        )

    return False, "No plateaus detected."


# ---------------------------------------------------------------------------
# Fix suggestions
# ---------------------------------------------------------------------------

_FIX_DATABASE: dict[str, list[str]] = {
    "divergence": [
        "Reduce `maxCo` in controlDict (try 0.3–0.5 for multiphase, 0.8 for single-phase)",
        "Check mesh quality with `checkMesh` — non-orthogonality > 85° causes divergence",
        "Add `nNonOrthogonalCorrectors 1` (or 2 for bad meshes) in the PIMPLE/PISO block",
        "Switch p_rgh solver from GAMG to PCG+DIC if mesh has high aspect-ratio cells",
        "Ensure boundary conditions are physically consistent (no fixed outflow with no inlet)",
        "Lower under-relaxation factors for pressure (0.3) and velocity (0.7) if steady-state",
    ],
    "oscillation": [
        "Reduce `maxCo` or `maxDeltaT` — oscillations often indicate the time step is too large",
        "Check for incorrect or inconsistent boundary conditions (pressure/velocity mismatch)",
        "Add `residualControl` to PIMPLE to improve outer-loop convergence per time step",
        "For p_rgh oscillations: increase `nCorrectors` from 3 to 5 in the PIMPLE block",
        "If using GAMG: reduce `agglomerator` smoothing or switch to PCG for stability",
        "Verify that `relaxationFactors` equations are set to 1 for transient simulations",
    ],
    "plateau": [
        "Check if source terms are correctly normalised — a stiff source term freezes residuals",
        "For species transport: lower the species under-relaxation factor to 0.2–0.4",
        "Verify DEFINE_ADJUST runs before the species solver (Fluent UDF execution order)",
        "Check for near-zero velocity regions — species diffusion dominates and slows convergence",
        "Consider refining the mesh near reaction zones to reduce the numerical Peclet number",
        "For calcocarbonic equilibrium: ensure pH is updated atomically with species concentrations",
        "Run more outer iterations per time step (nOuterCorrectors 2–5) before moving to next step",
    ],
    "continuity": [
        "High continuity error indicates mass imbalance — check inlet/outlet BC consistency",
        "Increase `nNonOrthogonalCorrectors` if mesh has high non-orthogonality",
        "Verify that compressible flow is not accidentally treated as incompressible",
        "Check that `fluxRequired` includes all relevant fields in fvSolution",
    ],
}


def suggest_fixes(issues: list[str]) -> list[str]:
    """Return actionable fix suggestions for detected issue types.

    Parameters
    ----------
    issues:
        List of issue type strings: 'divergence', 'oscillation', 'plateau',
        'continuity'. Unknown types are ignored.

    Returns
    -------
    Deduplicated list of suggestion strings.
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        key = issue.lower()
        for suggestion in _FIX_DATABASE.get(key, []):
            if suggestion not in seen:
                suggestions.append(suggestion)
                seen.add(suggestion)
    return suggestions


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_residuals(
    residuals_df: pd.DataFrame,
    output_path: str | Path,
    title: str = "CFD Residuals",
    time_col: str = "time",
    fields: list[str] | None = None,
) -> Path | None:
    """Plot residual curves to a PNG file.

    Parameters
    ----------
    residuals_df:
        DataFrame from load_openfoam_log() or parse_convergence_report().
    output_path:
        Path for the output PNG image.
    title:
        Figure title.
    fields:
        Subset of field names to plot. If None, plot all.

    Returns
    -------
    Path to the saved figure, or None if plotting failed.
    """
    if residuals_df.empty:
        log.warning("Empty DataFrame — no residuals to plot.")
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    col = "initial_residual" if "initial_residual" in residuals_df.columns else None
    x_col = time_col if time_col in residuals_df.columns else residuals_df.columns[0]

    # If 'field' column exists, pivot; otherwise treat each column as a field
    if "field" in residuals_df.columns and col:
        pivot = residuals_df.pivot_table(
            index=x_col, columns="field", values=col, aggfunc="first"
        )
    else:
        numeric_cols = residuals_df.select_dtypes(include="number").columns.tolist()
        pivot = residuals_df.set_index(numeric_cols[0])[numeric_cols[1:]]

    if fields:
        pivot = pivot[[c for c in fields if c in pivot.columns]]

    fig, ax = plt.subplots(figsize=(10, 5))
    for col_name in pivot.columns:
        ax.semilogy(pivot.index, pivot[col_name], lw=1.5, label=col_name)

    ax.axhline(1e-3, color="orange", ls="--", lw=1, alpha=0.6, label="1e-3 threshold")
    ax.axhline(1e-6, color="green",  ls="--", lw=1, alpha=0.6, label="1e-6 threshold")
    ax.set_xlabel(x_col.replace("_", " ").title())
    ax.set_ylabel("Initial Residual")
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(which="both", alpha=0.25)
    fig.tight_layout()

    try:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        log.info("Residual plot saved → %s", output_path)
    except OSError as exc:
        log.error("Could not save plot: %s", exc)
        return None
    finally:
        plt.close(fig)

    return output_path


# ---------------------------------------------------------------------------
# High-level analysis summary
# ---------------------------------------------------------------------------

def full_analysis(
    residuals_df: pd.DataFrame,
    output_plot: str | Path | None = None,
) -> dict[str, Any]:
    """Run all detectors and return a structured analysis dict.

    Returns
    -------
    dict with keys:
    - 'diverged': bool
    - 'oscillating': bool
    - 'plateaued': bool
    - 'explanations': list[str]
    - 'issues': list[str]  (issue type strings for suggest_fixes)
    - 'suggestions': list[str]
    - 'stats': dict with basic residual statistics
    - 'plot_path': str | None
    """
    residuals_df = _as_long_residuals(residuals_df)

    div, div_msg = detect_divergence(residuals_df)
    osc, osc_msg = detect_oscillations(residuals_df)
    plt_flag, plt_msg = detect_plateaus(residuals_df)

    issue_types: list[str] = []
    explanations: list[str] = []
    if div:
        issue_types.append("divergence")
        explanations.append(div_msg)
    if osc:
        issue_types.append("oscillation")
        explanations.append(osc_msg)
    if plt_flag:
        issue_types.append("plateau")
        explanations.append(plt_msg)

    suggestions = suggest_fixes(issue_types)

    # Basic statistics
    stats: dict[str, Any] = {}
    if not residuals_df.empty and "initial_residual" in residuals_df.columns:
        for field, grp in residuals_df.groupby("field"):
            vals = grp["initial_residual"].dropna()
            if vals.empty:
                continue
            stats[str(field)] = {
                "final": float(vals.iloc[-1]),
                "min": float(vals.min()),
                "max": float(vals.max()),
                "n_steps": len(vals),
            }

    plot_path: str | None = None
    if output_plot and not residuals_df.empty:
        saved = plot_residuals(residuals_df, output_plot)
        plot_path = str(saved) if saved else None

    return {
        "diverged": div,
        "oscillating": osc,
        "plateaued": plt_flag,
        "explanations": explanations if explanations else ["No issues detected — simulation appears healthy."],
        "issues": issue_types,
        "suggestions": suggestions,
        "stats": stats,
        "plot_path": plot_path,
    }
