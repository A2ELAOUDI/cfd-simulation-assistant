"""CFD assistant tool modules."""

from app.tools.analyze_convergence import (
    detect_divergence,
    detect_oscillations,
    detect_plateaus,
    full_analysis,
    load_openfoam_log,
    plot_residuals,
    suggest_fixes,
)
from app.tools.generate_report import generate_openfoam_report
from app.tools.parse_fluent import (
    detect_udf_issues,
    parse_convergence_report,
    parse_udf_file,
)
from app.tools.parse_openfoam import (
    detect_file_type,
    explain_file,
    parse_block_mesh_dict,
    parse_boundary_conditions,
    parse_control_dict,
    parse_fv_schemes,
    parse_fv_solution,
)

__all__ = [
    "parse_control_dict",
    "parse_fv_schemes",
    "parse_fv_solution",
    "parse_block_mesh_dict",
    "parse_boundary_conditions",
    "explain_file",
    "detect_file_type",
    "parse_udf_file",
    "detect_udf_issues",
    "parse_convergence_report",
    "load_openfoam_log",
    "detect_divergence",
    "detect_oscillations",
    "detect_plateaus",
    "suggest_fixes",
    "full_analysis",
    "plot_residuals",
    "generate_openfoam_report",
]
