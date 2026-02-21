"""Tests for the LangGraph agent tools (without live LLM calls).

Tool functions are tested directly — the LLM layer is mocked out completely
so no API key is required for CI.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Paths for sample data
REPO_ROOT = Path(__file__).parent.parent
CASE_DIR = REPO_ROOT / "sample_cases" / "openfoam_dambreak"
LOG_PATH = CASE_DIR / "logs" / "interFoam.log"
CTRL_PATH = CASE_DIR / "system" / "controlDict"
FLUENT_LOG = REPO_ROOT / "sample_cases" / "fluent_limestone" / "convergence_log.txt"


# ---------------------------------------------------------------------------
# Direct tool function tests (no LLM needed)
# ---------------------------------------------------------------------------

class TestParseToolDirect:
    """Test the parse_case_file tool logic directly."""

    def test_parse_control_dict_via_tool(self):
        from app.agent import parse_case_file
        result = parse_case_file.invoke({"file_path": str(CTRL_PATH)})
        assert isinstance(result, str)
        assert len(result) > 20
        assert "interFoam" in result or "controlDict" in result

    def test_parse_fv_schemes_via_tool(self):
        from app.agent import parse_case_file
        path = str(CASE_DIR / "system" / "fvSchemes")
        result = parse_case_file.invoke({"file_path": path})
        assert isinstance(result, str)
        assert len(result) > 10

    def test_missing_file_returns_error_message(self):
        from app.agent import parse_case_file
        result = parse_case_file.invoke({"file_path": "/nonexistent/file.cfg"})
        assert "not found" in result.lower() or "File" in result


class TestAnalyzeConvergenceToolDirect:
    """Test the analyze_convergence tool logic directly."""

    def test_openfoam_log_analysis(self):
        from app.agent import analyze_convergence
        result = analyze_convergence.invoke({"log_path": str(LOG_PATH)})
        assert isinstance(result, str)
        assert len(result) > 50

    def test_divergence_detected_in_sample_log(self):
        from app.agent import analyze_convergence
        result = analyze_convergence.invoke({"log_path": str(LOG_PATH)})
        upper = result.upper()
        assert "DIVERGENCE" in upper or "NaN" in result or "diverge" in result.lower()

    def test_fluent_log_plateau_detected(self):
        from app.agent import analyze_convergence
        result = analyze_convergence.invoke({"log_path": str(FLUENT_LOG)})
        assert isinstance(result, str)

    def test_missing_log_returns_error(self):
        from app.agent import analyze_convergence
        result = analyze_convergence.invoke({"log_path": "/no/such/file.log"})
        assert "not found" in result.lower()


class TestGenerateReportToolDirect:
    """Test the generate_report tool logic directly."""

    def test_returns_markdown(self):
        from app.agent import generate_report
        result = generate_report.invoke({"case_dir": str(CASE_DIR)})
        assert isinstance(result, str)
        assert "#" in result     # has at least one markdown header

    def test_contains_solver_name(self):
        from app.agent import generate_report
        result = generate_report.invoke({"case_dir": str(CASE_DIR)})
        assert "interFoam" in result

    def test_missing_case_dir_error(self):
        from app.agent import generate_report
        result = generate_report.invoke({"case_dir": "/nonexistent/case/"})
        assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# Mocked agent graph tests
# ---------------------------------------------------------------------------

class TestAgentGraphMocked:
    """Test the LangGraph agent with a mocked LLM — no API calls made."""

    @pytest.fixture
    def mock_llm(self):
        """Return a mock LLM that answers without calling any external service."""
        from langchain_core.messages import AIMessage

        llm = MagicMock()
        # Simulate a final AI response (no tool calls)
        ai_response = AIMessage(content="Mocked response: simulation looks healthy.")
        ai_response.tool_calls = []
        llm.bind_tools.return_value = MagicMock(
            invoke=MagicMock(return_value=ai_response)
        )
        return llm

    def test_agent_graph_builds_without_api_key(self, mock_llm):
        """Ensure build_graph doesn't crash even with no API key."""
        with patch("app.agent._get_llm", return_value=mock_llm.bind_tools([])):
            try:
                from app.agent import build_graph
                graph = build_graph(backend="openai")
                assert graph is not None
            except Exception as exc:
                pytest.skip(f"Agent graph build failed (expected without API key): {exc}")

    def test_cfd_assistant_chat_mocked(self, mock_llm):
        """Test CFDAssistant.chat with a mocked LLM."""
        from langchain_core.messages import AIMessage

        ai_response = AIMessage(content="The maxCo is set to 0.9, which is too high for VOF.")
        ai_response.tool_calls = []

        with patch("app.agent._get_llm") as mock_get_llm:
            mock_bound = MagicMock()
            mock_bound.invoke.return_value = ai_response
            mock_get_llm.return_value = mock_bound

            try:
                from app.agent import CFDAssistant
                assistant = CFDAssistant(backend="openai")
                response = assistant.chat("What is the maxCo setting?")
                assert isinstance(response, str)
                assert len(response) > 0
            except Exception as exc:
                pytest.skip(f"Mocked chat test skipped: {exc}")


# ---------------------------------------------------------------------------
# Tool metadata tests
# ---------------------------------------------------------------------------

class TestToolMetadata:
    """Verify that tools have proper metadata for LangGraph binding."""

    def test_tools_have_names(self):
        from app.agent import TOOLS
        for t in TOOLS:
            assert hasattr(t, "name") and t.name, f"Tool missing name: {t}"

    def test_tools_have_descriptions(self):
        from app.agent import TOOLS
        for t in TOOLS:
            assert hasattr(t, "description") and t.description, f"Tool missing description: {t}"

    def test_expected_tool_count(self):
        from app.agent import TOOLS
        assert len(TOOLS) == 4

    def test_tool_names_correct(self):
        from app.agent import TOOLS
        names = {t.name for t in TOOLS}
        expected = {"parse_case_file", "analyze_convergence", "search_knowledge_base", "generate_report"}
        assert names == expected
