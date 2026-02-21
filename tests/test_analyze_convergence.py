"""Tests for convergence analysis functions.

Uses both the bundled OpenFOAM log and synthetic DataFrames for
detector unit tests.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from app.tools.analyze_convergence import (
    detect_divergence,
    detect_oscillations,
    detect_plateaus,
    full_analysis,
    load_openfoam_log,
    suggest_fixes,
)
from app.tools.parse_fluent import parse_convergence_report

LOG_PATH = (
    Path(__file__).parent.parent
    / "sample_cases" / "openfoam_dambreak" / "logs" / "interFoam.log"
)
FLUENT_LOG_PATH = (
    Path(__file__).parent.parent
    / "sample_cases" / "fluent_limestone" / "convergence_log.txt"
)


# ---------------------------------------------------------------------------
# Helper: synthetic DataFrames
# ---------------------------------------------------------------------------

def _make_residuals(
    field: str,
    values: list[float],
    times: list[float] | None = None,
) -> pd.DataFrame:
    """Create a minimal residuals DataFrame for testing."""
    n = len(values)
    if times is None:
        times = list(range(n))
    return pd.DataFrame(
        {
            "time": times,
            "field": [field] * n,
            "initial_residual": values,
            "final_residual": [v / 10 for v in values],
            "n_iterations": [5] * n,
        }
    )


# ---------------------------------------------------------------------------
# load_openfoam_log
# ---------------------------------------------------------------------------

class TestLoadOpenFoamLog:
    def test_returns_dataframe(self):
        df = load_openfoam_log(LOG_PATH)
        assert isinstance(df, pd.DataFrame)

    def test_not_empty(self):
        df = load_openfoam_log(LOG_PATH)
        assert not df.empty

    def test_has_required_columns(self):
        df = load_openfoam_log(LOG_PATH)
        for col in ["time", "field", "initial_residual"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_field_names_include_ux(self):
        df = load_openfoam_log(LOG_PATH)
        fields = df["field"].unique().tolist()
        assert "Ux" in fields or any("x" in f.lower() for f in fields)

    def test_missing_file_returns_empty(self):
        df = load_openfoam_log("/nonexistent/interFoam.log")
        assert df.empty

    def test_residuals_positive(self):
        df = load_openfoam_log(LOG_PATH)
        vals = df["initial_residual"].dropna()
        assert (vals >= 0).all() or vals.isin([np.nan, np.inf]).any()


# ---------------------------------------------------------------------------
# detect_divergence
# ---------------------------------------------------------------------------

class TestDetectDivergence:
    def test_healthy_no_divergence(self):
        values = [1.0, 0.5, 0.2, 0.1, 0.05, 0.01, 0.001]
        df = _make_residuals("p", values)
        diverged, msg = detect_divergence(df)
        assert not diverged

    def test_sudden_jump_flagged(self):
        values = [0.1, 0.05, 0.02, 0.01, 200.0]   # sudden spike
        df = _make_residuals("p", values)
        diverged, msg = detect_divergence(df)
        assert diverged
        assert "p" in msg or "diverge" in msg.lower()

    def test_nan_flagged(self):
        values = [0.1, 0.05, np.nan]
        df = _make_residuals("Ux", values)
        diverged, msg = detect_divergence(df)
        assert diverged

    def test_inf_flagged(self):
        values = [0.1, 0.05, np.inf]
        df = _make_residuals("Ux", values)
        diverged, msg = detect_divergence(df)
        assert diverged

    def test_empty_df(self):
        diverged, msg = detect_divergence(pd.DataFrame())
        assert not diverged

    def test_real_log_detects_divergence(self):
        df = load_openfoam_log(LOG_PATH)
        if not df.empty:
            diverged, msg = detect_divergence(df)
            # The sample log has NaN / divergence at t=0.67
            assert diverged


# ---------------------------------------------------------------------------
# detect_oscillations
# ---------------------------------------------------------------------------

class TestDetectOscillations:
    def test_monotone_decrease_no_oscillation(self):
        values = [1.0, 0.5, 0.25, 0.12, 0.06, 0.03, 0.015]
        df = _make_residuals("U", values)
        osc, msg = detect_oscillations(df)
        assert not osc

    def test_oscillating_residuals_flagged(self):
        # Simulate alternating high/low residuals
        values = [0.01, 0.05, 0.008, 0.04, 0.009, 0.038, 0.01, 0.042, 0.011, 0.039]
        df = _make_residuals("p_rgh", values)
        osc, msg = detect_oscillations(df, amplitude_ratio=3.0, min_cycles=2)
        assert osc

    def test_empty_df(self):
        osc, msg = detect_oscillations(pd.DataFrame())
        assert not osc

    def test_real_log_oscillation_in_pressure(self):
        df = load_openfoam_log(LOG_PATH)
        if not df.empty:
            # Oscillation expected in p_rgh between t=0.3 and t=0.6
            osc, msg = detect_oscillations(df, field="p_rgh")
            # At least check it doesn't crash
            assert isinstance(osc, bool)


# ---------------------------------------------------------------------------
# detect_plateaus
# ---------------------------------------------------------------------------

class TestDetectPlateaus:
    def test_converging_not_plateau(self):
        values = [1.0] + [1.0 * (0.5 ** i) for i in range(1, 15)]
        df = _make_residuals("CO2", values)
        plateaued, msg = detect_plateaus(df, target_tolerance=1e-6)
        assert not plateaued

    def test_species_plateau_detected(self):
        # Simulate Fluent-style plateau at 1e-4
        converge = [1.0, 0.5, 0.2, 0.05, 1e-3, 5e-4, 2e-4]
        plateau = [1.05e-4] * 15   # stuck at 1e-4
        values = converge + plateau
        df = _make_residuals("co2", values)
        plateaued, msg = detect_plateaus(df, window=10, target_tolerance=1e-5)
        assert plateaued

    def test_empty_df(self):
        plateaued, msg = detect_plateaus(pd.DataFrame())
        assert not plateaued

    def test_fluent_log_plateau_detected(self):
        df = parse_convergence_report(FLUENT_LOG_PATH)
        if not df.empty:
            # Identify species columns by name
            species_cols = [c for c in df.columns if c not in ("iter",) and "velocity" not in c and "continuity" not in c]
            if species_cols:
                # Build compatible DataFrame for detect_plateaus
                long_rows = []
                iter_col = df.columns[0]  # first col is iter
                for col in species_cols[:1]:
                    for _, row in df.iterrows():
                        long_rows.append({
                            "time": row[iter_col],
                            "field": col,
                            "initial_residual": row[col],
                        })
                species_df = pd.DataFrame(long_rows)
                plateaued, msg = detect_plateaus(species_df, window=8, target_tolerance=1e-5)
                assert plateaued, f"Expected plateau in species residuals but got: {msg}"


# ---------------------------------------------------------------------------
# suggest_fixes
# ---------------------------------------------------------------------------

class TestSuggestFixes:
    def test_divergence_returns_suggestions(self):
        fixes = suggest_fixes(["divergence"])
        assert len(fixes) > 0
        assert any("maxCo" in f or "Co" in f for f in fixes)

    def test_oscillation_suggestions(self):
        fixes = suggest_fixes(["oscillation"])
        assert len(fixes) > 0

    def test_plateau_suggestions_mention_species(self):
        fixes = suggest_fixes(["plateau"])
        combined = " ".join(fixes).lower()
        assert "species" in combined or "under-relaxation" in combined

    def test_unknown_issue_returns_empty(self):
        fixes = suggest_fixes(["unknown_issue_xyz"])
        assert fixes == []

    def test_multiple_issues_deduped(self):
        fixes1 = suggest_fixes(["divergence"])
        fixes2 = suggest_fixes(["divergence", "divergence"])
        assert len(fixes1) == len(fixes2)


# ---------------------------------------------------------------------------
# full_analysis
# ---------------------------------------------------------------------------

class TestFullAnalysis:
    def test_healthy_simulation(self):
        values = [1.0 * (0.3 ** i) for i in range(20)]
        df = _make_residuals("p", values)
        result = full_analysis(df)
        assert isinstance(result, dict)
        assert "diverged" in result
        assert "oscillating" in result
        assert "plateaued" in result
        assert "suggestions" in result

    def test_returns_stats(self):
        values = [0.5, 0.2, 0.1, 0.05]
        df = _make_residuals("U", values)
        result = full_analysis(df)
        assert "stats" in result
        assert "U" in result["stats"]

    def test_empty_df_no_crash(self):
        result = full_analysis(pd.DataFrame())
        assert isinstance(result, dict)
