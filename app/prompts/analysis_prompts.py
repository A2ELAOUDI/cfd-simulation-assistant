"""Structured prompt templates for CFD analysis tasks."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# File explanation prompts
# ---------------------------------------------------------------------------

FILE_EXPLANATION_TEMPLATE = """You are a CFD expert. Explain the following {file_type} file content
to a simulation engineer. Be specific about what each setting means physically and numerically.

File content:
```
{content}
```

Provide:
1. A one-paragraph summary of what this file configures
2. A table of key parameters with their values and physical meaning
3. Any potential issues or non-standard settings you notice
4. Recommendations for improvement if applicable
"""

OPENFOAM_DICT_TEMPLATE = """Analyze this OpenFOAM {dict_name} dictionary and explain:
- What solver/algorithm it configures
- Whether the settings are appropriate for the described physics: {physics_description}
- Any inconsistencies between settings

Dictionary content:
```
{content}
```
"""

# ---------------------------------------------------------------------------
# Convergence analysis prompts
# ---------------------------------------------------------------------------

CONVERGENCE_SUMMARY_TEMPLATE = """Given this convergence analysis of a CFD simulation, provide a
structured diagnosis:

Detected issues:
{issues_json}

Residual statistics:
{stats_json}

Please provide:
1. Root cause analysis for each detected issue
2. Ordered list of recommended fixes (most impactful first)
3. Expected outcome after applying fixes
4. Monitoring advice for the re-run

Format your response as a structured engineering report.
"""

DIVERGENCE_DIAGNOSIS_TEMPLATE = """A CFD simulation diverged with the following signature:
- Last stable time/iteration: {last_stable}
- Field that diverged first: {first_diverged_field}
- Residual at divergence: {divergence_residual}
- Courant number at divergence (if available): {courant_number}

Context:
{context}

Diagnose the most likely cause and provide a step-by-step fix procedure.
"""

# ---------------------------------------------------------------------------
# Report generation prompt
# ---------------------------------------------------------------------------

REPORT_TEMPLATE = """Generate a professional CFD simulation analysis report in Markdown format.

Case information:
{case_info}

Include the following sections:
1. Executive Summary (2-3 sentences)
2. Simulation Setup (solver, domain, mesh, BCs)
3. Numerical Schemes (from fvSchemes)
4. Linear Solver Settings (from fvSolution)
5. Convergence Analysis (if log data available)
6. Issues and Recommendations
7. Next Steps

Use tables where appropriate. Be technically precise.
"""

# ---------------------------------------------------------------------------
# Knowledge base query rewriting
# ---------------------------------------------------------------------------

QUERY_REWRITE_TEMPLATE = """Rewrite this user question as a precise technical query
to search a CFD knowledge base. Extract key technical terms.

User question: {user_question}

Rewritten query (include solver names, parameter names, error messages if present):"""

# ---------------------------------------------------------------------------
# UDF analysis
# ---------------------------------------------------------------------------

UDF_ANALYSIS_TEMPLATE = """Analyze this ANSYS Fluent UDF code and:
1. List all DEFINE_* macros used and their purpose
2. Identify which zones/surfaces they apply to
3. Flag any potential issues (thread safety, missing guards, unit errors)
4. Explain the physical model being implemented

UDF content:
```c
{udf_content}
```
"""
