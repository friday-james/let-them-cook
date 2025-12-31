#!/usr/bin/env python3
"""
Let Them Cook - Autonomous Claude Code Watcher

Watches Claude Code's session in real-time and chimes in when needed.
Works like a pair programmer watching over your shoulder.

How it works:
1. Tails Claude Code's session JSONL file
2. Analyzes each response from Claude
3. Decides if it should chime in with guidance
4. Sends follow-up messages using --continue

Usage:
    ./let_them_cook.py                      # Watch current session
    ./let_them_cook.py --task "Build API"   # Start with a task
    ./let_them_cook.py --passive            # Only watch, don't intervene
"""

import asyncio
import json
import os
import sys
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv()


# =============================================================================
# CONFIGURATION
# =============================================================================

CLAUDE_BIN = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Colors
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    CLAUDE = "\033[38;5;141m"      # Purple
    COOK = "\033[38;5;208m"        # Orange
    TOOL = "\033[38;5;39m"         # Blue
    RESULT = "\033[38;5;245m"      # Gray
    SUCCESS = "\033[38;5;82m"      # Green
    ERROR = "\033[38;5;196m"       # Red
    INFO = "\033[38;5;248m"        # Light gray
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"


# =============================================================================
# GEMINI CLIENT
# =============================================================================

class GeminiClient:
    """Gemini client for deciding when to chime in"""

    def __init__(self, model: str = "gemini-2.0-flash"):
        self.model_name = model
        self.available = False

        try:
            import google.generativeai as genai
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(model)
                self.available = True
        except Exception as e:
            print(f"{C.ERROR}[!] Gemini not available: {e}{C.RESET}")

    def analyze(self, prompt: str, max_tokens: int = 500) -> str:
        if not self.available:
            return ""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={"max_output_tokens": max_tokens}
            )
            return response.text.strip()
        except Exception as e:
            print(f"{C.ERROR}[gemini:error] {e}{C.RESET}")
            return ""


# =============================================================================
# SESSION WATCHER
# =============================================================================

@dataclass
class Message:
    role: str
    content: str
    timestamp: str
    tool_calls: List[Dict] = None


def get_project_session_dir() -> Path:
    """Get session directory for current working directory"""
    cwd = os.getcwd()
    project_name = cwd.replace("/", "-")
    return CLAUDE_PROJECTS_DIR / project_name


def get_latest_session_file() -> Optional[Path]:
    """Find the most recent session file"""
    session_dir = get_project_session_dir()
    if not session_dir.exists():
        return None

    jsonl_files = list(session_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonl_files[0]


def parse_session_line(line: str) -> Optional[Message]:
    """Parse a single JSONL line from Claude's session"""
    try:
        data = json.loads(line.strip())
        msg_type = data.get("type")

        if msg_type == "user":
            content = data.get("message", {}).get("content", "")
            return Message(
                role="user",
                content=content,
                timestamp=data.get("timestamp", "")
            )

        elif msg_type == "assistant":
            msg = data.get("message", {})
            content_blocks = msg.get("content", [])

            text_parts = []
            tool_calls = []

            for block in content_blocks:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "name": block.get("name", ""),
                            "input": block.get("input", {})
                        })

            return Message(
                role="assistant",
                content="\n".join(text_parts),
                timestamp=data.get("timestamp", ""),
                tool_calls=tool_calls if tool_calls else None
            )

    except json.JSONDecodeError:
        pass

    return None


class SessionWatcher:
    """Watches Claude Code session and decides when to intervene"""

    def __init__(
        self,
        task: str = None,
        passive: bool = False,
        aggressive: bool = True,
        model: str = "sonnet",
    ):
        self.task = task
        self.passive = passive
        self.aggressive = aggressive
        self.model = model
        self.gemini = GeminiClient()
        self.conversation: List[Message] = []
        self.last_position = 0
        self.running = False
        self.session_file: Optional[Path] = None

    def should_chime_in(self, latest_message: Message) -> Optional[str]:
        """Ask Gemini if we should send a follow-up"""
        if self.passive or not self.gemini.available:
            return None

        # Build context
        recent = self.conversation[-6:]
        context = "\n".join([
            f"{m.role.upper()}: {m.content[:400]}"
            for m in recent
        ])

        task_context = f"ORIGINAL TASK: {self.task}\n" if self.task else ""

        aggressive_note = """
IMPORTANT: Be proactive. If there's ANY opportunity to push forward, take it.
Look for:
- Things Claude could improve
- Next logical steps
- Errors or issues to address
- Ways to make the solution more complete
""" if self.aggressive else ""

        prompt = f"""You are a pair programmer watching Claude Code work.
{task_context}{aggressive_note}
Claude just said:
---
{latest_message.content[:1500]}
---

Tool calls made: {json.dumps(latest_message.tool_calls) if latest_message.tool_calls else "None"}

Recent conversation:
{context}

Should you chime in? Consider:
1. Is Claude stuck or going in the wrong direction?
2. Is there an obvious next step Claude should take?
3. Did Claude make an error that needs correction?
4. Is the task incomplete and needs more work?

If YES - provide your message to Claude (be specific and actionable)
If NO - respond with exactly: [SILENT]

Your response:"""

        response = self.gemini.analyze(prompt, max_tokens=400)

        if "[SILENT]" in response or not response:
            return None

        return response.strip()

    async def send_to_claude(self, message: str):
        """Send a message to Claude using --continue"""
        cmd = [
            CLAUDE_BIN,
            "-p",
            "--model", self.model,
            "--dangerously-skip-permissions",
            "--continue",
            message
        ]

        print(f"\n{C.COOK}{C.BOLD}[cook]{C.RESET} {C.COOK}{message}{C.RESET}\n")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        response = stdout.decode('utf-8', errors='replace').strip()

        print(f"{C.DIM}[sent - Claude will respond in session]{C.RESET}\n")

    async def tail_session(self):
        """Tail the session file and react to new messages"""
        print(f"{C.INFO}[watcher] Looking for session file...{C.RESET}")

        # Wait for session file
        while self.running:
            self.session_file = get_latest_session_file()
            if self.session_file and self.session_file.stat().st_size > 0:
                break
            await asyncio.sleep(1)

        if not self.running:
            return

        print(f"{C.SUCCESS}[watcher] Found: {self.session_file.name}{C.RESET}")
        print(f"{C.DIM}[watcher] Tailing session...{C.RESET}\n")

        # Read existing content
        with open(self.session_file) as f:
            for line in f:
                msg = parse_session_line(line)
                if msg:
                    self.conversation.append(msg)
            self.last_position = f.tell()

        # Tail for new content
        while self.running:
            try:
                with open(self.session_file) as f:
                    f.seek(self.last_position)
                    new_lines = f.readlines()
                    self.last_position = f.tell()

                for line in new_lines:
                    msg = parse_session_line(line)
                    if msg:
                        self.conversation.append(msg)
                        await self.handle_message(msg)

                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"{C.ERROR}[watcher:error] {e}{C.RESET}")
                await asyncio.sleep(1)

    async def handle_message(self, msg: Message):
        """Handle a new message from the session"""
        if msg.role == "user":
            print(f"{C.GREEN}[user]{C.RESET} {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}")

        elif msg.role == "assistant":
            # Show Claude's response
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    print(f"{C.TOOL}[tool] {tc['name']}{C.RESET}")

            if msg.content:
                preview = msg.content[:200].replace('\n', ' ')
                print(f"{C.CLAUDE}[claude]{C.RESET} {preview}{'...' if len(msg.content) > 200 else ''}")

            # Decide if we should chime in
            if not self.passive:
                chime = self.should_chime_in(msg)
                if chime:
                    await asyncio.sleep(2)  # Brief pause
                    await self.send_to_claude(chime)

    async def start_task(self, task: str):
        """Start Claude with an initial task"""
        self.task = task

        cmd = [
            CLAUDE_BIN,
            "-p",
            "--model", self.model,
            "--dangerously-skip-permissions",
            task
        ]

        print(f"{C.COOK}{C.BOLD}[cook]{C.RESET} {C.COOK}Starting: {task}{C.RESET}\n")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Don't wait for completion - just start it
        # The tail will pick up the response

    async def run(self):
        """Main run loop"""
        print(f"\n{C.CYAN}{'═' * 60}")
        print(f"🍳 LET THEM COOK - Autonomous Watcher")
        print(f"{'═' * 60}{C.RESET}")
        print(f"{C.INFO}Mode: {'Passive (watch only)' if self.passive else 'Active (will chime in)'}{C.RESET}")
        print(f"{C.INFO}Model: {C.CLAUDE}{self.model}{C.RESET}")
        print(f"{C.INFO}Gemini: {C.COOK}{self.gemini.model_name if self.gemini.available else 'off'}{C.RESET}")
        print(f"\n{C.DIM}Press Ctrl+C to stop{C.RESET}")
        print(f"{C.CYAN}{'═' * 60}{C.RESET}\n")

        self.running = True

        try:
            # Start initial task if provided
            if self.task:
                await self.start_task(self.task)
                await asyncio.sleep(2)

            # Start tailing
            await self.tail_session()

        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}[stopped]{C.RESET}")
        finally:
            self.running = False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Let Them Cook - Claude Watcher")
    parser.add_argument("--task", "-t", help="Initial task to start")
    parser.add_argument("--passive", "-p", action="store_true",
                        help="Passive mode - watch only, don't intervene")
    parser.add_argument("--no-aggressive", action="store_true",
                        help="Less aggressive - only chime in when necessary")
    parser.add_argument("-m", "--model", default="sonnet",
                        help="Claude model to use")

    args = parser.parse_args()

    if not os.path.exists(CLAUDE_BIN):
        print(f"{C.ERROR}[!] Claude Code not found{C.RESET}")
        sys.exit(1)

    watcher = SessionWatcher(
        task=args.task,
        passive=args.passive,
        aggressive=not args.no_aggressive,
        model=args.model,
    )

    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
