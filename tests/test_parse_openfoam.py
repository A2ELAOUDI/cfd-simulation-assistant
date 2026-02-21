"""Tests for OpenFOAM file parsers.

All tests use the sample cases bundled with the repo — no OpenFOAM installation
required.
"""

import pytest
from pathlib import Path

from app.tools.parse_openfoam import (
    detect_file_type,
    explain_file,
    parse_block_mesh_dict,
    parse_boundary_conditions,
    parse_control_dict,
    parse_fv_schemes,
    parse_fv_solution,
)

# Resolve sample case paths via conftest
CASE_DIR = Path(__file__).parent.parent / "sample_cases" / "openfoam_dambreak"
SYSTEM_DIR = CASE_DIR / "system"


# ---------------------------------------------------------------------------
# parse_control_dict
# ---------------------------------------------------------------------------

class TestParseControlDict:
    def test_returns_dict(self):
        result = parse_control_dict(SYSTEM_DIR / "controlDict")
        assert isinstance(result, dict)

    def test_application_key(self):
        result = parse_control_dict(SYSTEM_DIR / "controlDict")
        assert result.get("application") == "interFoam"

    def test_end_time(self):
        result = parse_control_dict(SYSTEM_DIR / "controlDict")
        assert float(result.get("endTime", 0)) == pytest.approx(2.5)

    def test_adjust_time_step(self):
        result = parse_control_dict(SYSTEM_DIR / "controlDict")
        # Can be "yes" or True depending on parser
        assert result.get("adjustTimeStep") in (True, "yes")

    def test_missing_file_returns_empty(self):
        result = parse_control_dict("/nonexistent/path/controlDict")
        assert result == {}

    def test_no_foam_file_key(self):
        result = parse_control_dict(SYSTEM_DIR / "controlDict")
        assert "FoamFile" not in result


# ---------------------------------------------------------------------------
# parse_fv_schemes
# ---------------------------------------------------------------------------

class TestParseFvSchemes:
    def test_returns_dict(self):
        result = parse_fv_schemes(SYSTEM_DIR / "fvSchemes")
        assert isinstance(result, dict)

    def test_has_ddt_schemes(self):
        result = parse_fv_schemes(SYSTEM_DIR / "fvSchemes")
        assert "ddtSchemes" in result

    def test_ddt_default_euler(self):
        result = parse_fv_schemes(SYSTEM_DIR / "fvSchemes")
        ddt = result.get("ddtSchemes", {})
        assert isinstance(ddt, dict)
        assert "default" in ddt

    def test_has_div_schemes(self):
        result = parse_fv_schemes(SYSTEM_DIR / "fvSchemes")
        assert "divSchemes" in result

    def test_missing_file_graceful(self):
        result = parse_fv_schemes("/nonexistent/fvSchemes")
        assert result == {}


# ---------------------------------------------------------------------------
# parse_fv_solution
# ---------------------------------------------------------------------------

class TestParseFvSolution:
    def test_returns_dict(self):
        result = parse_fv_solution(SYSTEM_DIR / "fvSolution")
        assert isinstance(result, dict)

    def test_has_solvers_key(self):
        result = parse_fv_solution(SYSTEM_DIR / "fvSolution")
        assert "solvers" in result

    def test_solvers_is_dict(self):
        result = parse_fv_solution(SYSTEM_DIR / "fvSolution")
        solvers = result.get("solvers", {})
        assert isinstance(solvers, dict)

    def test_pimple_block_present(self):
        result = parse_fv_solution(SYSTEM_DIR / "fvSolution")
        assert "PIMPLE" in result

    def test_missing_file_graceful(self):
        result = parse_fv_solution("/nonexistent/fvSolution")
        assert result == {}


# ---------------------------------------------------------------------------
# parse_block_mesh_dict
# ---------------------------------------------------------------------------

class TestParseBlockMeshDict:
    def test_returns_dict(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        assert isinstance(result, dict)

    def test_has_scale_key(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        assert "scale" in result

    def test_scale_is_one(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        assert float(result.get("scale", -1)) == pytest.approx(1.0)

    def test_total_cells_positive(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        assert result.get("total_cells", 0) > 0

    def test_has_patches(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        patches = result.get("patches", [])
        assert isinstance(patches, list)

    def test_patch_names_include_walls(self):
        result = parse_block_mesh_dict(SYSTEM_DIR / "blockMeshDict")
        patch_names = [p.get("name", "") for p in result.get("patches", [])]
        # At least one patch should contain "Wall" or "wall"
        assert any("wall" in name.lower() or "Wall" in name for name in patch_names)

    def test_missing_file_graceful(self):
        result = parse_block_mesh_dict("/nonexistent/blockMeshDict")
        assert result == {}


# ---------------------------------------------------------------------------
# explain_file
# ---------------------------------------------------------------------------

class TestExplainFile:
    def test_control_dict_explanation_not_empty(self):
        text = (SYSTEM_DIR / "controlDict").read_text()
        result = explain_file("controlDict", text)
        assert len(result) > 50

    def test_control_dict_explanation_contains_solver(self):
        text = (SYSTEM_DIR / "controlDict").read_text()
        result = explain_file("controlDict", text)
        assert "interFoam" in result

    def test_fv_schemes_explanation_mentions_schemes(self):
        text = (SYSTEM_DIR / "fvSchemes").read_text()
        result = explain_file("fvSchemes", text)
        assert "ddtSchemes" in result or "divSchemes" in result


# ---------------------------------------------------------------------------
# detect_file_type
# ---------------------------------------------------------------------------

class TestDetectFileType:
    def test_control_dict(self):
        assert detect_file_type(SYSTEM_DIR / "controlDict") == "controlDict"

    def test_fv_schemes(self):
        assert detect_file_type(SYSTEM_DIR / "fvSchemes") == "fvSchemes"

    def test_fv_solution(self):
        assert detect_file_type(SYSTEM_DIR / "fvSolution") == "fvSolution"

    def test_block_mesh_dict(self):
        assert detect_file_type(SYSTEM_DIR / "blockMeshDict") == "blockMeshDict"
