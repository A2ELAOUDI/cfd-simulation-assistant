"""LangGraph ReAct agent for CFD simulation assistance.

The agent is built around four tools:
  - parse_case_file    : parse and explain any CFD configuration file
  - analyze_convergence: run convergence diagnostics on log files
  - search_knowledge_base: RAG retrieval from the CFD knowledge base
  - generate_report    : create a full case analysis report

Supports both OpenAI and Anthropic LLM backends, configured via .env.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Sequence

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

load_dotenv()

log = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ---------------------------------------------------------------------------
# Tool definitions (LangChain @tool decorated)
# ---------------------------------------------------------------------------

@tool
def parse_case_file(file_path: str) -> str:
    """Parse and explain a CFD configuration file.

    Accepts any OpenFOAM dictionary file (controlDict, fvSchemes, fvSolution,
    blockMeshDict) or ANSYS Fluent UDF (.c file) or convergence report.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the CFD file to parse.

    Returns
    -------
    A structured explanation of the file contents.
    """
    from app.tools.parse_openfoam import detect_file_type, explain_file, _read_file
    from app.tools.parse_fluent import parse_udf_file, detect_udf_issues

    path = Path(file_path)
    if not path.exists():
        return f"File not found: {file_path}"

    suffix = path.suffix.lower()
    name = path.name.lower()

    # Fluent UDF
    if suffix in (".c", ".h") or "udf" in name:
        info = parse_udf_file(path)
        macros = info.get("macros", [])
        issues = info.get("issues", [])
        lines = [
            f"## UDF Analysis: `{path.name}`\n",
            f"**DEFINE_* macros found ({len(macros)}):**",
        ]
        for m in macros:
            lines.append(f"- `{m['macro']}({m['name']})` at line {m['line']}")
        if issues:
            lines.append(f"\n**Issues detected ({len(issues)}):**")
            for iss in issues:
                lines.append(
                    f"- [{iss['severity'].upper()}] line {iss['line']}: "
                    f"{iss['description']} → {iss['suggestion']}"
                )
        return "\n".join(lines)

    # OpenFOAM dictionary
    text = _read_file(path) or ""
    file_type = detect_file_type(path)
    return explain_file(file_type, text)


@tool
def analyze_convergence(log_path: str, output_plot: str = "") -> str:
    """Analyze a CFD convergence log file for issues.

    Works with OpenFOAM solver logs (interFoam, pimpleFoam, simpleFoam, etc.)
    and ANSYS Fluent convergence CSV/TXT exports.

    Parameters
    ----------
    log_path : str
        Path to the log or residual file.
    output_plot : str, optional
        If provided, save a residual plot PNG to this path.

    Returns
    -------
    A structured convergence analysis report as text.
    """
    from app.tools.analyze_convergence import (
        full_analysis,
        load_openfoam_log,
    )
    from app.tools.parse_fluent import parse_convergence_report

    path = Path(log_path)
    if not path.exists():
        return f"Log file not found: {log_path}"

    # Try OpenFOAM log format first
    df = load_openfoam_log(path)
    if df.empty:
        # Try Fluent residual format
        df = parse_convergence_report(path)

    if df.empty:
        return f"Could not parse residual data from `{log_path}`. Verify the file format."

    analysis = full_analysis(df, output_plot=output_plot if output_plot else None)

    lines = [
        f"## Convergence Analysis: `{path.name}`\n",
        f"**Rows parsed:** {len(df)}  ",
        f"**Fields detected:** {', '.join(f'`{f}`' for f in df.get('field', pd.Series()).unique()) if 'field' in df.columns else str(len(df.columns) - 1) + ' columns'}\n",
    ]

    status_parts = []
    if analysis["diverged"]:
        status_parts.append("❌ DIVERGENCE")
    if analysis["oscillating"]:
        status_parts.append("⚠️ OSCILLATIONS")
    if analysis["plateaued"]:
        status_parts.append("⚠️ PLATEAU")
    if not status_parts:
        status_parts.append("✅ HEALTHY")

    lines.append(f"**Status:** {' | '.join(status_parts)}\n")
    lines.append("**Findings:**")
    for exp in analysis["explanations"]:
        lines.append(f"- {exp}")

    if analysis["stats"]:
        lines.append("\n**Final residuals:**")
        for field, st in analysis["stats"].items():
            lines.append(
                f"- `{field}`: final={st['final']:.2e}, "
                f"min={st['min']:.2e}, max={st['max']:.2e}"
            )

    if analysis["suggestions"]:
        lines.append("\n**Recommended fixes (priority order):**")
        for i, sug in enumerate(analysis["suggestions"], 1):
            lines.append(f"{i}. {sug}")

    if analysis.get("plot_path"):
        lines.append(f"\n📊 Residual plot saved → `{analysis['plot_path']}`")

    return "\n".join(lines)


@tool
def search_knowledge_base(query: str) -> str:
    """Search the CFD knowledge base using semantic retrieval (RAG).

    Use this tool to look up:
    - OpenFOAM solver descriptions and use cases
    - Boundary condition types and parameters
    - Numerical scheme recommendations
    - Common errors and their fixes
    - ANSYS Fluent UDF macros and usage
    - Porous media and species transport setup

    Parameters
    ----------
    query : str
        Natural language or technical question about CFD simulation.

    Returns
    -------
    Relevant documentation excerpts from the knowledge base.
    """
    from app.rag.retriever import retrieve_and_format

    context = retrieve_and_format(query, k=4)
    return f"## Knowledge Base Results for: `{query}`\n\n{context}"


@tool
def generate_report(case_dir: str, output_path: str = "") -> str:
    """Generate a full analysis report for an OpenFOAM case directory.

    Parses all standard case files (controlDict, fvSchemes, fvSolution,
    blockMeshDict, boundary conditions) and any available log files.

    Parameters
    ----------
    case_dir : str
        Path to the OpenFOAM case directory.
    output_path : str, optional
        If provided, save the Markdown report to this path.

    Returns
    -------
    The complete Markdown report as a string.
    """
    from app.tools.generate_report import generate_openfoam_report

    path = Path(case_dir)
    if not path.exists():
        return f"Case directory not found: {case_dir}"

    return generate_openfoam_report(
        case_dir=path,
        output_path=output_path if output_path else None,
    )


# Collect tools for binding
TOOLS = [parse_case_file, analyze_convergence, search_knowledge_base, generate_report]


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _get_llm(backend: str | None = None):
    """Return the configured LLM with tools bound."""
    backend = backend or os.getenv("LLM_BACKEND", "openai")

    if backend == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        llm = ChatAnthropic(model=model, temperature=0, max_tokens=4096)
    else:
        from langchain_openai import ChatOpenAI
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model, temperature=0)

    return llm.bind_tools(TOOLS)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "You are an expert CFD simulation assistant. "
            "Help engineers with OpenFOAM and ANSYS Fluent simulations."
        )


def build_graph(backend: str | None = None) -> Any:
    """Build and compile the LangGraph ReAct agent graph.

    Parameters
    ----------
    backend:
        'openai' or 'anthropic'. Reads from LLM_BACKEND env var if None.

    Returns
    -------
    Compiled LangGraph graph ready for invocation.
    """
    llm_with_tools = _get_llm(backend)
    system_prompt = _load_system_prompt()
    tool_node = ToolNode(TOOLS)

    def agent_node(state: AgentState) -> dict:
        messages = state["messages"]
        # Prepend system prompt if not already there
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=system_prompt)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph.compile()


# ---------------------------------------------------------------------------
# High-level chat interface
# ---------------------------------------------------------------------------

class CFDAssistant:
    """Stateful CFD simulation assistant wrapping the LangGraph agent."""

    def __init__(self, backend: str | None = None) -> None:
        self.graph = build_graph(backend)
        self._history: list[BaseMessage] = []

    def chat(self, user_message: str) -> str:
        """Send a message and return the assistant's response.

        Maintains conversation history across calls.
        """
        self._history.append(HumanMessage(content=user_message))
        result = self.graph.invoke({"messages": self._history})
        ai_message = result["messages"][-1]
        self._history = result["messages"]
        return ai_message.content

    def reset(self) -> None:
        """Clear conversation history."""
        self._history = []

    def analyze_file(self, file_path: str) -> str:
        """One-shot file analysis without history."""
        self.reset()
        return self.chat(f"Please analyze this CFD file: {file_path}")

    def analyze_case(self, case_dir: str) -> str:
        """One-shot full case analysis without history."""
        self.reset()
        return self.chat(
            f"Generate a full analysis report for the OpenFOAM case at: {case_dir}"
        )


# ---------------------------------------------------------------------------
# Needed for analyze_convergence tool (pandas import guard)
# ---------------------------------------------------------------------------
try:
    import pandas as pd  # noqa: F401
except ImportError:
    pass
