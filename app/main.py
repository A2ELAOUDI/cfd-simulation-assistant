"""CLI entry point for the CFD Simulation Assistant.

Usage
-----
python -m app.main                              # interactive chat
python -m app.main --analyze path/to/file       # one-shot file analysis
python -m app.main --case path/to/case_dir      # one-shot case analysis
python -m app.main --report path/ -o report.md  # generate report
python -m app.main --backend anthropic           # choose LLM backend
python -m app.main --index                       # rebuild knowledge base index
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.rule import Rule
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

BANNER = """
╔═══════════════════════════════════════════════════════════╗
║           CFD Simulation Assistant                        ║
║    OpenFOAM · ANSYS Fluent · LangGraph RAG               ║
╚═══════════════════════════════════════════════════════════╝
Type your question or file path. Commands: /reset /quit /help
"""

HELP_TEXT = """
**Available commands:**
- `/reset`       — Clear conversation history
- `/quit` or `/exit` — Exit the assistant
- `/analyze <path>` — Analyze a specific CFD file
- `/report <dir>`   — Generate a case report
- `/index`          — Rebuild the knowledge base index
- `/help`           — Show this help

**Example questions:**
- "What does vanLeer mean in fvSchemes?"
- "Analyze the controlDict at sample_cases/openfoam_dambreak/system/controlDict"
- "My p_rgh residuals are oscillating. What should I fix?"
- "Explain DEFINE_SOURCE with the dS linearisation derivative"
"""


def _print(msg: str, console=None) -> None:
    if HAS_RICH and console:
        console.print(Markdown(msg))
    else:
        print(msg)


def _get_assistant(backend: str):
    """Build the CFD assistant, handling missing API keys gracefully."""
    try:
        from app.agent import CFDAssistant
        return CFDAssistant(backend=backend)
    except Exception as exc:
        print(f"\n[ERROR] Could not initialise LLM agent: {exc}")
        print("Check your .env file — copy .env.example and set your API key.\n")
        sys.exit(1)


def cmd_interactive(backend: str) -> None:
    """Run the interactive chat loop."""
    assistant = _get_assistant(backend)

    if HAS_RICH:
        console = Console()
        console.print(Panel(BANNER.strip(), style="bold cyan"))
        console.print(f"[dim]Backend: {backend} | Type /help for commands[/dim]\n")
    else:
        print(BANNER)
        print(f"Backend: {backend}\n")

    while True:
        try:
            if HAS_RICH:
                user_input = Prompt.ask("[bold green]You[/bold green]")
            else:
                user_input = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input.strip():
            continue

        # Handle slash commands
        if user_input.startswith("/quit") or user_input.startswith("/exit"):
            print("Goodbye.")
            break

        if user_input.startswith("/reset"):
            assistant.reset()
            print("Conversation history cleared.")
            continue

        if user_input.startswith("/help"):
            _print(HELP_TEXT, console if HAS_RICH else None)
            continue

        if user_input.startswith("/analyze "):
            file_path = user_input[9:].strip()
            user_input = f"Please analyze this CFD file in detail: {file_path}"

        if user_input.startswith("/report "):
            case_dir = user_input[8:].strip()
            user_input = f"Generate a full analysis report for the OpenFOAM case at: {case_dir}"

        if user_input.startswith("/index"):
            try:
                from app.rag.indexer import build_index
                build_index(force=True)
                print("Knowledge base index rebuilt.")
            except Exception as exc:
                print(f"Index build failed: {exc}")
            continue

        # Normal LLM call
        try:
            response = assistant.chat(user_input)
            if HAS_RICH:
                console.print(Rule(style="dim"))
                console.print("[bold blue]Assistant[/bold blue]")
                console.print(Markdown(response))
                console.print()
            else:
                print(f"\nAssistant:\n{response}\n")
        except Exception as exc:
            print(f"[ERROR] {exc}")


def cmd_analyze(file_path: str, backend: str) -> None:
    """Analyze a single file and print the result."""
    assistant = _get_assistant(backend)
    result = assistant.analyze_file(file_path)
    if HAS_RICH:
        Console().print(Markdown(result))
    else:
        print(result)


def cmd_case(case_dir: str, backend: str) -> None:
    """Analyze a full case directory."""
    assistant = _get_assistant(backend)
    result = assistant.analyze_case(case_dir)
    if HAS_RICH:
        Console().print(Markdown(result))
    else:
        print(result)


def cmd_report(case_dir: str, output: str | None, backend: str) -> None:
    """Generate and save a Markdown report."""
    from app.tools.generate_report import generate_openfoam_report

    report = generate_openfoam_report(
        case_dir=case_dir,
        output_path=output,
    )
    if output:
        print(f"Report written → {output}")
    else:
        if HAS_RICH:
            Console().print(Markdown(report))
        else:
            print(report)


def cmd_index() -> None:
    """Rebuild the FAISS knowledge base index."""
    from app.rag.indexer import build_index
    build_index(force=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="CFD Simulation Assistant — AI-powered analysis for OpenFOAM and Fluent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--backend",
        choices=["openai", "anthropic"],
        default=None,
        help="LLM backend (default: reads LLM_BACKEND from .env)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--analyze", metavar="FILE", help="Analyze a specific CFD file")
    group.add_argument("--case", metavar="DIR", help="Analyze a full OpenFOAM case directory")
    group.add_argument("--report", metavar="DIR", help="Generate a full case analysis report")
    group.add_argument("--index", action="store_true", help="Rebuild the knowledge base index")
    p.add_argument("-o", "--output", metavar="PATH", help="Output path for --report")
    return p.parse_args()


def main() -> None:
    import os
    args = parse_args()
    backend = args.backend or os.getenv("LLM_BACKEND", "openai")

    if args.index:
        cmd_index()
    elif args.analyze:
        cmd_analyze(args.analyze, backend)
    elif args.case:
        cmd_case(args.case, backend)
    elif args.report:
        cmd_report(args.report, args.output, backend)
    else:
        cmd_interactive(backend)


if __name__ == "__main__":
    main()
