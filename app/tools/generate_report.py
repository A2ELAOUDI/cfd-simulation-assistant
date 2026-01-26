"""Generate structured Markdown simulation analysis reports.

Combines parsed OpenFOAM case data, convergence analysis, and LLM-generated
insights into a professional engineering report.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.tools.analyze_convergence import full_analysis, load_openfoam_log
from app.tools.parse_openfoam import (
    detect_file_type,
    parse_block_mesh_dict,
    parse_boundary_conditions,
    parse_control_dict,
    parse_fv_schemes,
    parse_fv_solution,
)

log = logging.getLogger(__name__)


def _fmt_dict(d: dict, indent: int = 0) -> str:
    """Render a dict as a Markdown definition list."""
    lines = []
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}- **{k}:**")
            lines.append(_fmt_dict(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{prefix}- **{k}:** {', '.join(str(i) for i in v[:5])}")
        else:
            lines.append(f"{prefix}- **{k}:** `{v}`")
    return "\n".join(lines)


def _find_logs(case_dir: Path) -> list[Path]:
    """Find all solver log files in a case directory."""
    log_files: list[Path] = []
    for pattern in ("*.log", "logs/*.log", "log.*", "log"):
        log_files.extend(case_dir.glob(pattern))
    return sorted(log_files)


def generate_openfoam_report(
    case_dir: str | Path,
    output_path: str | Path | None = None,
    include_convergence: bool = True,
) -> str:
    """Generate a full analysis report for an OpenFOAM case directory.

    Parameters
    ----------
    case_dir:
        Path to the case directory (containing 0/, constant/, system/).
    output_path:
        If provided, write the report Markdown to this file.
    include_convergence:
        Whether to analyse solver logs if found.

    Returns
    -------
    Markdown string of the full report.
    """
    case_dir = Path(case_dir)
    sections: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- Header ----
    sections.append(
        f"# CFD Simulation Analysis Report\n"
        f"**Case:** `{case_dir.name}`  \n"
        f"**Generated:** {now}  \n"
        f"**Tool:** CFD Simulation Assistant\n"
    )

    # ---- 1. controlDict ----
    ctrl_path = case_dir / "system" / "controlDict"
    ctrl = {}
    if ctrl_path.exists():
        ctrl = parse_control_dict(ctrl_path)
        sections.append("## 1. Simulation Control (`controlDict`)\n")
        solver = ctrl.get("application", "unknown")
        sections.append(f"| Parameter | Value |")
        sections.append(f"|-----------|-------|")
        for key in [
            "application", "startTime", "endTime", "deltaT",
            "adjustTimeStep", "maxCo", "maxDeltaT", "writeInterval",
        ]:
            val = ctrl.get(key, "—")
            sections.append(f"| `{key}` | `{val}` |")
    else:
        sections.append("## 1. Simulation Control\n_controlDict not found._\n")

    # ---- 2. Mesh ----
    bm_path = case_dir / "system" / "blockMeshDict"
    if bm_path.exists():
        mesh = parse_block_mesh_dict(bm_path)
        sections.append("\n## 2. Mesh (`blockMeshDict`)\n")
        sections.append(f"| Property | Value |")
        sections.append(f"|----------|-------|")
        sections.append(f"| Blocks   | {mesh.get('n_blocks', '?')} |")
        sections.append(f"| Total cells | {mesh.get('total_cells', '?'):,} |")
        sections.append(f"| Scale factor | {mesh.get('scale', 1.0)} |")
        patches = mesh.get("patches", [])
        if patches:
            sections.append(f"\n**Patches ({len(patches)}):**")
            for p in patches:
                sections.append(f"- `{p.get('name', '?')}` — {p.get('type', '?')}")
    else:
        sections.append("\n## 2. Mesh\n_blockMeshDict not found._\n")

    # ---- 3. Boundary Conditions ----
    bcs = parse_boundary_conditions(case_dir)
    if bcs:
        sections.append("\n## 3. Boundary Conditions\n")
        for field, patches in bcs.items():
            sections.append(f"### `{field}`\n")
            sections.append("| Patch | Type | Value |")
            sections.append("|-------|------|-------|")
            if isinstance(patches, dict):
                for patch, bc in patches.items():
                    bc_type = bc.get("type", "?") if isinstance(bc, dict) else str(bc)
                    bc_val = bc.get("value", "—") if isinstance(bc, dict) else "—"
                    sections.append(f"| `{patch}` | `{bc_type}` | `{bc_val}` |")
    else:
        sections.append("\n## 3. Boundary Conditions\n_No 0/ directory or field files found._\n")

    # ---- 4. Numerical Schemes ----
    fvs_path = case_dir / "system" / "fvSchemes"
    if fvs_path.exists():
        schemes = parse_fv_schemes(fvs_path)
        sections.append("\n## 4. Numerical Schemes (`fvSchemes`)\n")
        for scheme_type in [
            "ddtSchemes", "gradSchemes", "divSchemes",
            "laplacianSchemes", "snGradSchemes",
        ]:
            sub = schemes.get(scheme_type, {})
            if sub and isinstance(sub, dict):
                sections.append(f"**{scheme_type}:**")
                for k, v in sub.items():
                    sections.append(f"- `{k}`: `{v}`")
                sections.append("")
    else:
        sections.append("\n## 4. Numerical Schemes\n_fvSchemes not found._\n")

    # ---- 5. Linear Solvers ----
    fvsol_path = case_dir / "system" / "fvSolution"
    if fvsol_path.exists():
        solution = parse_fv_solution(fvsol_path)
        sections.append("\n## 5. Linear Solvers (`fvSolution`)\n")
        solvers = solution.get("solvers", {})
        if solvers and isinstance(solvers, dict):
            sections.append("| Field | Solver | Tolerance | RelTol |")
            sections.append("|-------|--------|-----------|--------|")
            for field, settings in solvers.items():
                if not isinstance(settings, dict):
                    continue
                sections.append(
                    f"| `{field}` | `{settings.get('solver','?')}` "
                    f"| `{settings.get('tolerance','?')}` "
                    f"| `{settings.get('relTol','?')}` |"
                )
        for algo in ("PIMPLE", "SIMPLE", "PISO"):
            sub = solution.get(algo, {})
            if sub and isinstance(sub, dict):
                sections.append(f"\n**{algo} algorithm:**")
                for k, v in sub.items():
                    sections.append(f"- `{k}`: `{v}`")
    else:
        sections.append("\n## 5. Linear Solvers\n_fvSolution not found._\n")

    # ---- 6. Convergence Analysis ----
    if include_convergence:
        log_files = _find_logs(case_dir)
        if log_files:
            sections.append("\n## 6. Convergence Analysis\n")
            for log_file in log_files[:2]:  # analyse up to 2 log files
                sections.append(f"### Log: `{log_file.name}`\n")
                df = load_openfoam_log(log_file)
                if df.empty:
                    sections.append("_Could not parse residuals from this log._\n")
                    continue

                analysis = full_analysis(df)
                status_icon = "✅" if not any(
                    [analysis["diverged"], analysis["oscillating"], analysis["plateaued"]]
                ) else "⚠️"
                sections.append(f"{status_icon} **Status:**")
                for exp in analysis["explanations"]:
                    sections.append(f"- {exp}")

                if analysis["stats"]:
                    sections.append("\n**Final residuals:**")
                    sections.append("| Field | Final residual | Min | Max | Steps |")
                    sections.append("|-------|----------------|-----|-----|-------|")
                    for field, st in analysis["stats"].items():
                        sections.append(
                            f"| `{field}` | `{st['final']:.2e}` "
                            f"| `{st['min']:.2e}` | `{st['max']:.2e}` "
                            f"| {st['n_steps']} |"
                        )

                if analysis["suggestions"]:
                    sections.append("\n**Recommendations:**")
                    for i, sug in enumerate(analysis["suggestions"], 1):
                        sections.append(f"{i}. {sug}")
        else:
            sections.append("\n## 6. Convergence Analysis\n_No log files found._\n")

    # ---- 7. Issues & Next Steps ----
    sections.append("\n## 7. Next Steps\n")
    sections.append(
        "- Run `checkMesh` to verify mesh quality (non-orthogonality < 70°, max skewness < 4)\n"
        "- Run `foamDictionary -entry application -value system/controlDict` to verify solver\n"
        "- Monitor `Courant Number max` during first few time steps\n"
        "- Set `writeInterval` to capture enough snapshots for post-processing\n"
    )

    # ---- Footer ----
    sections.append(
        "\n---\n_Generated by [CFD Simulation Assistant](https://github.com/abdou-elaoudi/cfd-simulation-assistant)_"
    )

    report = "\n".join(sections)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        log.info("Report written → %s", out)

    return report
