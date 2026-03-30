"""Mini Harness — Landing Knowledge Assistant.

Usage:
    land                             # Analyze current directory
    land /path/to/repo               # Analyze specific project
    land -p "分析这个项目的架构"       # One-shot mode
    land --session 2026-03-30-143022 # Resume session
"""

from __future__ import annotations

import argparse
import os
import sys

from harness.llm import LLMClient
from harness.tools import registry
from harness.memory import MemoryStore
from harness.safety import SafetyGuard
from harness.agent import Agent


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

class _C:
    GRAY = "\033[90m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Special commands
# ---------------------------------------------------------------------------

def handle_special(cmd: str, agent: Agent) -> bool:
    """Handle /commands. Returns True if handled."""
    cmd = cmd.strip()

    if cmd == "/quit" or cmd == "/exit":
        agent.memory.save()
        print(f"\n{_C.GREEN}Memory saved. Session: {agent.memory.session_id}{_C.RESET}")
        print(f"{_C.GRAY}Goodbye!{_C.RESET}")
        sys.exit(0)

    if cmd == "/memory":
        print(f"\n{_C.CYAN}{agent.memory.summary()}{_C.RESET}\n")
        return True

    if cmd == "/output":
        output_dir = "output"
        if os.path.isdir(output_dir):
            for root, dirs, files in os.walk(output_dir):
                level = root.replace(output_dir, "").count(os.sep)
                indent = "  " * level
                print(f"{_C.CYAN}{indent}{os.path.basename(root)}/{_C.RESET}")
                sub_indent = "  " * (level + 1)
                for f in files:
                    print(f"{_C.GRAY}{sub_indent}{f}{_C.RESET}")
        else:
            print(f"{_C.GRAY}(output/ directory is empty){_C.RESET}")
        print()
        return True

    if cmd == "/session":
        print(f"\n{_C.CYAN}Session ID: {agent.memory.session_id}")
        print(f"Project: {agent.project_path or '(none)'}")
        print(f"History: {len(agent.history)} messages")
        print(f"Memory: {len(agent.memory.get_all())} facts{_C.RESET}\n")
        return True

    if cmd == "/sessions":
        sessions = agent.memory.list_sessions()
        if sessions:
            print(f"\n{_C.CYAN}Available sessions:{_C.RESET}")
            for s in sessions:
                print(f"  {_C.GRAY}{s}{_C.RESET}")
        else:
            print(f"{_C.GRAY}(no saved sessions){_C.RESET}")
        print()
        return True

    if cmd == "/help":
        print(f"""
{_C.BOLD}Special commands:{_C.RESET}
  {_C.CYAN}/memory{_C.RESET}     — Show memorized facts
  {_C.CYAN}/output{_C.RESET}     — Show output directory tree
  {_C.CYAN}/session{_C.RESET}    — Show current session info
  {_C.CYAN}/sessions{_C.RESET}   — List all saved sessions
  {_C.CYAN}/help{_C.RESET}       — Show this help
  {_C.CYAN}/quit{_C.RESET}       — Save memory and exit
""")
        return True

    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="land — Landing Knowledge Assistant",
        usage="land [path] [-p PROMPT] [--session ID]",
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path (default: current directory)")
    parser.add_argument("-p", "--prompt", type=str, default="", help="One-shot prompt (non-interactive)")
    parser.add_argument("--session", type=str, default="", help="Resume a saved session")
    args = parser.parse_args()

    # --- Init components ---
    print(f"{_C.BOLD}land v0.1 — Landing Knowledge Assistant{_C.RESET}")
    print(f"{_C.GRAY}Type /help for commands, /quit to exit{_C.RESET}\n")

    try:
        llm = LLMClient()
    except ValueError as e:
        print(f"{_C.RED}Error: {e}{_C.RESET}")
        print(f"{_C.GRAY}Set GLM_API_KEY environment variable. See: .env.example{_C.RESET}")
        sys.exit(1)

    memory = MemoryStore(session_id=args.session)
    safety = SafetyGuard()

    project_path = os.path.abspath(args.path)
    print(f"{_C.GREEN}Project: {project_path}{_C.RESET}")

    print(f"{_C.GRAY}Session: {memory.session_id}{_C.RESET}")
    if memory.get_all():
        print(f"{_C.GRAY}Loaded {len(memory.get_all())} facts from previous session{_C.RESET}")
    print()

    agent = Agent(
        llm=llm,
        tools=registry,
        memory=memory,
        safety=safety,
        project_path=project_path,
    )

    # --- One-shot mode ---
    if args.prompt:
        try:
            response = agent.run(args.prompt)
            print(f"\n{response}\n")
        except Exception as e:
            print(f"\n{_C.RED}Error: {e}{_C.RESET}\n")
            sys.exit(1)
        agent.memory.save()
        return

    # --- REPL ---
    while True:
        try:
            user_input = input(f"{_C.BOLD}> {_C.RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            handle_special("/quit", agent)

        if not user_input:
            continue

        # Special commands
        if user_input.startswith("/"):
            if handle_special(user_input, agent):
                continue
            print(f"{_C.YELLOW}Unknown command: {user_input}. Type /help{_C.RESET}\n")
            continue

        # Run agent
        try:
            response = agent.run(user_input)
            print(f"\n{response}\n")
        except KeyboardInterrupt:
            print(f"\n{_C.YELLOW}(interrupted){_C.RESET}\n")
        except Exception as e:
            print(f"\n{_C.RED}Error: {e}{_C.RESET}\n")


if __name__ == "__main__":
    main()
