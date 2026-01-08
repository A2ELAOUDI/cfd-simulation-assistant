"""Parse OpenFOAM case files into structured Python dictionaries.

Handles the OpenFOAM C++-style dictionary format with nested blocks,
inline comments (// and /* */), and the FoamFile header.

All functions return empty dicts / None on malformed input — no exceptions
propagate to the caller.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Low-level OpenFOAM dictionary parser
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    """Remove C-style block comments and line comments."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _tokenize(text: str) -> list[str]:
    """Split cleaned text into tokens (words, brackets, semicolons)."""
    return re.findall(r"[^\s;(){}\[\]]+|[;(){}\[\]]", text)


def _parse_value(tokens: list[str], pos: int) -> tuple[Any, int]:
    """Recursively parse a value starting at tokens[pos].

    Returns (parsed_value, new_position).
    """
    if pos >= len(tokens):
        return None, pos

    tok = tokens[pos]

    if tok == "{":
        # Nested dict block
        d: dict[str, Any] = {}
        pos += 1
        while pos < len(tokens) and tokens[pos] != "}":
            if tokens[pos] == ";":
                pos += 1
                continue
            key = tokens[pos]
            pos += 1
            if pos < len(tokens) and tokens[pos] == "{":
                val, pos = _parse_value(tokens, pos)
            elif pos < len(tokens) and tokens[pos] == ";":
                val = None
                pos += 1
            else:
                val_tokens: list[str] = []
                while pos < len(tokens) and tokens[pos] not in (";", "}"):
                    val_tokens.append(tokens[pos])
                    pos += 1
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1
                val = " ".join(val_tokens) if val_tokens else None
            d[key] = val
        if pos < len(tokens) and tokens[pos] == "}":
            pos += 1
        return d, pos

    if tok in ("(", "["):
        close = ")" if tok == "(" else "]"
        items: list[Any] = []
        pos += 1
        while pos < len(tokens) and tokens[pos] != close:
            if tokens[pos] in (";", ","):
                pos += 1
                continue
            item, pos = _parse_value(tokens, pos)
            items.append(item)
        if pos < len(tokens):
            pos += 1
        return items, pos

    # Scalar / string token
    return _coerce(tok), pos + 1


def _coerce(value: str) -> Any:
    """Try to convert a string token to int, float, or leave as str."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() == "yes":
        return True
    if value.lower() == "no":
        return False
    return value


def _parse_foam_dict(text: str) -> dict[str, Any]:
    """Parse a full OpenFOAM dictionary text into a Python dict."""
    clean = _strip_comments(text)
    tokens = _tokenize(clean)
    result: dict[str, Any] = {}
    pos = 0
    while pos < len(tokens):
        if tokens[pos] in (";", "}"):
            pos += 1
            continue
        if pos + 1 < len(tokens) and tokens[pos + 1] == "{":
            key = tokens[pos]
            val, pos = _parse_value(tokens, pos + 1)
            result[key] = val
        elif pos + 1 < len(tokens) and tokens[pos + 1] not in ("{", "}", ";"):
            key = tokens[pos]
            # Collect value until semicolon
            pos += 1
            val_toks: list[str] = []
            while pos < len(tokens) and tokens[pos] != ";":
                if tokens[pos] in ("{", "}"):
                    break
                val_toks.append(tokens[pos])
                pos += 1
            if pos < len(tokens) and tokens[pos] == ";":
                pos += 1
            result[key] = _coerce(" ".join(val_toks)) if val_toks else None
        else:
            pos += 1
    return result


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_control_dict(path: str | Path) -> dict[str, Any]:
    """Parse an OpenFOAM controlDict file.

    Returns
    -------
    dict with keys like 'application', 'startTime', 'endTime', 'deltaT',
    'writeInterval', 'maxCo', etc. Returns empty dict on failure.
    """
    text = _read_file(Path(path))
    if text is None:
        return {}
    try:
        raw = _parse_foam_dict(text)
        # Remove FoamFile header from result
        raw.pop("FoamFile", None)
        return raw
    except Exception as exc:
        log.error("parse_control_dict failed for %s: %s", path, exc)
        return {}


def parse_fv_schemes(path: str | Path) -> dict[str, Any]:
    """Parse an OpenFOAM fvSchemes file.

    Returns
    -------
    dict with sub-dicts for each scheme category:
    'ddtSchemes', 'gradSchemes', 'divSchemes', 'laplacianSchemes',
    'interpolationSchemes', 'snGradSchemes'.
    """
    text = _read_file(Path(path))
    if text is None:
        return {}
    try:
        raw = _parse_foam_dict(text)
        raw.pop("FoamFile", None)
        return raw
    except Exception as exc:
        log.error("parse_fv_schemes failed for %s: %s", path, exc)
        return {}


def parse_fv_solution(path: str | Path) -> dict[str, Any]:
    """Parse an OpenFOAM fvSolution file.

    Returns
    -------
    dict with sub-dicts 'solvers' (per-field settings) and algorithm
    dicts ('PIMPLE', 'SIMPLE', 'PISO', etc.).
    """
    text = _read_file(Path(path))
    if text is None:
        return {}
    try:
        raw = _parse_foam_dict(text)
        raw.pop("FoamFile", None)
        return raw
    except Exception as exc:
        log.error("parse_fv_solution failed for %s: %s", path, exc)
        return {}


def parse_block_mesh_dict(path: str | Path) -> dict[str, Any]:
    """Parse an OpenFOAM blockMeshDict and extract high-level mesh info.

    Returns
    -------
    dict with keys:
    - 'scale': mesh scale factor
    - 'n_blocks': number of hex blocks
    - 'patches': list of patch names and types
    - 'total_cells': estimated total cell count
    - 'raw': full parsed dict
    """
    text = _read_file(Path(path))
    if text is None:
        return {}
    try:
        raw = _parse_foam_dict(text)
        raw.pop("FoamFile", None)

        # Count blocks by looking for "hex" occurrences
        n_blocks = len(re.findall(r"\bhex\b", text or ""))

        # Extract patch names from boundary section
        patches: list[dict[str, str]] = []
        boundary_match = re.findall(
            r"(\w+)\s*\{[^}]*type\s+(\w+)[^}]*\}", text, re.DOTALL
        )
        for name, btype in boundary_match:
            if name not in ("FoamFile", "blocks", "vertices", "edges", "mergePatchPairs"):
                patches.append({"name": name, "type": btype})

        # Estimate total cells from first block
        total_cells = 0
        block_cell_match = re.findall(r"hex\s*\([^)]+\)\s*\((\d+)\s+(\d+)\s+(\d+)\)", text)
        for nx, ny, nz in block_cell_match:
            total_cells += int(nx) * int(ny) * int(nz)

        return {
            "scale": raw.get("scale", 1.0),
            "n_blocks": n_blocks,
            "patches": patches,
            "total_cells": total_cells,
            "raw": raw,
        }
    except Exception as exc:
        log.error("parse_block_mesh_dict failed for %s: %s", path, exc)
        return {}


def parse_boundary_conditions(case_path: str | Path) -> dict[str, dict[str, Any]]:
    """Parse all boundary condition files in the 0/ directory of a case.

    Returns
    -------
    dict mapping field name → dict of patches → BC dict.
    e.g. {'U': {'inlet': {'type': 'fixedValue', 'value': '...'}}, ...}
    """
    case = Path(case_path)
    zero_dir = case / "0"
    if not zero_dir.exists():
        log.warning("No 0/ directory found in %s", case)
        return {}

    result: dict[str, dict[str, Any]] = {}
    for field_file in sorted(zero_dir.iterdir()):
        if field_file.is_file():
            text = _read_file(field_file)
            if text is None:
                continue
            try:
                parsed = _parse_foam_dict(text)
                boundary = parsed.get("boundaryField", {})
                if boundary:
                    result[field_file.name] = boundary
            except Exception as exc:
                log.warning("Could not parse BC file %s: %s", field_file, exc)

    return result


def explain_file(file_type: str, content: str) -> str:
    """Return a structured human-readable explanation of an OpenFOAM file.

    Parameters
    ----------
    file_type:
        One of 'controlDict', 'fvSchemes', 'fvSolution', 'blockMeshDict',
        'boundary_condition', 'transportProperties', or 'unknown'.
    content:
        Raw file text.

    Returns
    -------
    A multiline string description of the file's role and key settings.
    """
    lines: list[str] = []

    if file_type == "controlDict":
        parsed = _parse_foam_dict(content)
        parsed.pop("FoamFile", None)
        lines.append("## controlDict — Simulation Control")
        lines.append(f"- **Solver:** `{parsed.get('application', 'unknown')}`")
        lines.append(f"- **Start time:** {parsed.get('startTime', '?')} s")
        lines.append(f"- **End time:** {parsed.get('endTime', '?')} s")
        lines.append(f"- **Time step (deltaT):** {parsed.get('deltaT', '?')} s")
        lines.append(f"- **Adaptive time-stepping:** {parsed.get('adjustTimeStep', 'no')}")
        if parsed.get("adjustTimeStep") in (True, "yes"):
            lines.append(f"  - maxCo = {parsed.get('maxCo', '?')}")
            lines.append(f"  - maxDeltaT = {parsed.get('maxDeltaT', '?')} s")
        lines.append(f"- **Write interval:** {parsed.get('writeInterval', '?')} s")

    elif file_type == "fvSchemes":
        parsed = _parse_foam_dict(content)
        parsed.pop("FoamFile", None)
        lines.append("## fvSchemes — Numerical Discretisation")
        for scheme_type in [
            "ddtSchemes", "gradSchemes", "divSchemes",
            "laplacianSchemes", "snGradSchemes",
        ]:
            sub = parsed.get(scheme_type, {})
            if sub:
                lines.append(f"\n### {scheme_type}")
                if isinstance(sub, dict):
                    for k, v in sub.items():
                        lines.append(f"- `{k}`: {v}")

    elif file_type == "fvSolution":
        parsed = _parse_foam_dict(content)
        parsed.pop("FoamFile", None)
        lines.append("## fvSolution — Linear Solver Configuration")
        solvers = parsed.get("solvers", {})
        if solvers:
            lines.append("\n### Per-field solvers")
            for field, settings in solvers.items():
                if isinstance(settings, dict):
                    lines.append(
                        f"- **{field}**: {settings.get('solver', '?')} "
                        f"(tol={settings.get('tolerance', '?')})"
                    )
        for algo in ("PIMPLE", "SIMPLE", "PISO"):
            sub = parsed.get(algo, {})
            if sub and isinstance(sub, dict):
                lines.append(f"\n### {algo} algorithm")
                for k, v in sub.items():
                    lines.append(f"- {k}: {v}")

    else:
        lines.append(f"## {file_type}")
        lines.append("_(Generic OpenFOAM dictionary — detailed parsing not available for this type)_")
        parsed = _parse_foam_dict(content)
        parsed.pop("FoamFile", None)
        for k, v in list(parsed.items())[:20]:
            lines.append(f"- **{k}:** {v}")

    return "\n".join(lines)


def detect_file_type(path: str | Path) -> str:
    """Infer the OpenFOAM file type from its name or FoamFile header."""
    name = Path(path).name
    known = {
        "controlDict": "controlDict",
        "fvSchemes": "fvSchemes",
        "fvSolution": "fvSolution",
        "blockMeshDict": "blockMeshDict",
        "setFieldsDict": "setFieldsDict",
        "transportProperties": "transportProperties",
        "turbulenceProperties": "turbulenceProperties",
        "decomposeParDict": "decomposeParDict",
    }
    if name in known:
        return known[name]
    text = _read_file(Path(path)) or ""
    m = re.search(r'object\s+(\w+)', text)
    return m.group(1) if m else "unknown"
