"""Parse ANSYS Fluent input files: UDFs, convergence reports, and setup descriptions.

All functions return empty structures on malformed/missing input.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UDF parsing
# ---------------------------------------------------------------------------

# All DEFINE_* macros registered in Fluent UDF API
_DEFINE_MACROS = [
    "DEFINE_SOURCE", "DEFINE_INIT", "DEFINE_ADJUST", "DEFINE_ON_DEMAND",
    "DEFINE_PROFILE", "DEFINE_CG_MOTION", "DEFINE_PROPERTY", "DEFINE_DIFFUSIVITY",
    "DEFINE_UDS_FLUX", "DEFINE_UDS_UNSTEADY", "DEFINE_EXECUTE_AT_END",
    "DEFINE_EXECUTE_AT_START", "DEFINE_EXECUTE_EVERY_N_ITER",
    "DEFINE_HEAT_FLUX", "DEFINE_MASS_TRANSFER", "DEFINE_REACTION_RATE",
    "DEFINE_NET_REACTION_RATE", "DEFINE_NOX_RATE", "DEFINE_SOX_RATE",
    "DEFINE_TURBULENT_VISCOSITY", "DEFINE_VAPORIZATION_RATE",
]

# Common Fluent cell-loop macros
_LOOP_MACROS = [
    "begin_c_loop", "end_c_loop", "begin_f_loop", "end_f_loop",
    "begin_c_loop_int", "end_c_loop_int",
]

# Parallel-safety red flags
_PARALLEL_RISKS = [
    "printf",       # not parallel-safe; use Message()
    "fopen",        # file I/O is not distributed; guard with if (I_AM_NODE_ZERO)
    "exit(",        # aborts all processes; use Error() instead
    "static ",      # static variables are not safe across threads
]


def parse_udf_file(path: str | Path) -> dict[str, Any]:
    """Extract structure from an ANSYS Fluent UDF file.

    Parameters
    ----------
    path : path to the .c or .h UDF file

    Returns
    -------
    dict with keys:
    - 'macros': list of dicts with keys 'macro', 'name', 'line'
    - 'species_referenced': list of species strings found
    - 'zones_referenced': list of zone IDs/names referenced
    - 'includes': list of #include headers
    - 'udm_usage': list of C_UDMI / C_UDSI accesses found
    - 'issues': list of potential problems detected
    """
    text = _read_file(Path(path))
    if text is None:
        return {
            "macros": [], "species_referenced": [],
            "zones_referenced": [], "includes": [],
            "udm_usage": [], "issues": [],
        }

    macros: list[dict[str, Any]] = []
    for macro_name in _DEFINE_MACROS:
        for m in re.finditer(rf"\b{re.escape(macro_name)}\s*\(\s*(\w+)", text):
            line_no = text[: m.start()].count("\n") + 1
            macros.append(
                {"macro": macro_name, "name": m.group(1), "line": line_no}
            )

    includes = re.findall(r'#\s*include\s*[<"]([^>"]+)[>"]', text)

    # Look for species references (e.g. MIXTURE_SPECIES, TP_RANS_SPECIES)
    species = list(set(re.findall(r'SV_Y_\d+|"([a-z0-9]+)"', text)))
    species = [s for s in species if s]  # drop empty

    # Zone ID integers after THREAD_ID() or in zone arrays
    zones = list(set(re.findall(r"THREAD_ID\s*\(\s*(\w+)\s*\)|zone_ID\s*=\s*(\d+)", text)))

    # UDM / UDS accesses
    udm_usage = list(set(
        re.findall(r"C_UDMI\s*\([^,]+,\s*(\d+)\)", text)
        + re.findall(r"C_UDSI\s*\([^,]+,\s*(\d+)\)", text)
    ))

    issues = detect_udf_issues(text)

    return {
        "macros": macros,
        "species_referenced": species,
        "zones_referenced": [z for pair in zones for z in pair if z],
        "includes": includes,
        "udm_usage": udm_usage,
        "issues": issues,
    }


def detect_udf_issues(udf_content: str) -> list[dict[str, str]]:
    """Scan UDF source for common problems.

    Returns
    -------
    list of dicts with 'severity', 'line', 'description', 'suggestion'
    """
    issues: list[dict[str, str]] = []
    lines = udf_content.splitlines()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # printf without parallel guard
        if "printf" in stripped and "I_AM_NODE_ZERO" not in udf_content:
            issues.append({
                "severity": "warning",
                "line": str(i),
                "description": "`printf` used without parallel guard",
                "suggestion": (
                    "Wrap with `if (I_AM_NODE_ZERO) { ... }` or replace with `Message()`"
                ),
            })
            break  # report once per file

        # fopen without node-zero guard
        if "fopen" in stripped and "I_AM_NODE_ZERO" not in udf_content:
            issues.append({
                "severity": "error",
                "line": str(i),
                "description": "`fopen` in parallel UDF without node-zero guard",
                "suggestion": (
                    "File I/O only works on node 0 in parallel. Wrap with "
                    "`if (I_AM_NODE_ZERO) { ... }` and use `PRF_GSYNC()` after."
                ),
            })
            break

    # exit() usage
    if re.search(r"\bexit\s*\(", udf_content):
        issues.append({
            "severity": "error",
            "line": "?",
            "description": "`exit()` called inside UDF",
            "suggestion": "Replace with `Error(\"message\")` — exit() kills all MPI ranks.",
        })

    # DEFINE_SOURCE returning a float without setting dS correctly
    for m in re.finditer(r"DEFINE_SOURCE\s*\(\s*\w+", udf_content):
        block_start = m.end()
        # Look for dS assignment in next ~30 lines
        surrounding = udf_content[block_start : block_start + 800]
        if "dS[eqn]" not in surrounding:
            issues.append({
                "severity": "warning",
                "line": str(udf_content[:block_start].count("\n") + 1),
                "description": "DEFINE_SOURCE does not set dS[eqn] (linearisation derivative)",
                "suggestion": (
                    "Add `dS[eqn] = d(source)/d(phi)` for better convergence. "
                    "Set to 0.0 if source is constant."
                ),
            })

    # Missing udf.h include
    if "udf.h" not in udf_content:
        issues.append({
            "severity": "error",
            "line": "1",
            "description": "`#include \"udf.h\"` not found",
            "suggestion": "Add `#include \"udf.h\"` as the first line of your UDF file.",
        })

    return issues


# ---------------------------------------------------------------------------
# Convergence report parsing
# ---------------------------------------------------------------------------

def parse_convergence_report(path: str | Path) -> pd.DataFrame:
    """Parse an ANSYS Fluent convergence residual report.

    Fluent exports residuals as a space/tab-separated file with a header row:
        iter   continuity   x-velocity   y-velocity   ...   species-0   species-1

    Returns
    -------
    DataFrame with columns ['iter', field1, field2, ...] indexed by iteration.
    Empty DataFrame on failure.
    """
    text = _read_file(Path(path))
    if text is None:
        return pd.DataFrame()

    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("!")]

    # Find the header line (contains 'iter' or 'Iteration')
    header_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"iter|Iteration", line, re.IGNORECASE):
            header_idx = i
            break

    if header_idx is None:
        # Fallback: try to detect purely numeric table
        log.warning("No header found in %s — attempting headerless parse", path)
        return _parse_headerless_residuals(lines)

    header = lines[header_idx].split()
    # Normalise column names
    header = [h.lower().replace("-", "_").replace(" ", "_") for h in header]

    rows: list[list[float]] = []
    for line in lines[header_idx + 1 :]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            rows.append([float(p) for p in parts[: len(header)]])
        except ValueError:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=header[: len(rows[0])])
    return df


def _parse_headerless_residuals(lines: list[str]) -> pd.DataFrame:
    """Best-effort parse when no header row is present."""
    rows: list[list[float]] = []
    for line in lines:
        try:
            rows.append([float(x) for x in line.split()])
        except ValueError:
            continue
    if not rows:
        return pd.DataFrame()
    n_cols = max(len(r) for r in rows)
    cols = ["iter"] + [f"residual_{i}" for i in range(n_cols - 1)]
    return pd.DataFrame(
        [r + [None] * (n_cols - len(r)) for r in rows],
        columns=cols,
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return None
