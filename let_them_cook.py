#!/usr/bin/env python3
"""
Let Them Cook - Autonomous Claude + Gemini Collaboration

Two AI agents cooking together:
- Gemini (cook) drives the direction and decides next steps
- Claude Code executes, writes code, uses tools
- User can interrupt and join anytime

Modes:
1. Drive mode (default): Gemini actively drives Claude through tasks
2. Watch mode: Tail existing session and chime in when needed

Usage:
    ./let_them_cook.py "Build a REST API"         # Drive Claude through task
    ./let_them_cook.py --watch                    # Watch existing session
    ./let_them_cook.py --passive                  # Watch only, don't intervene
"""

import asyncio
import json
import os
import sys
import shutil
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
    """Gemini client for driving Claude and deciding when to chime in"""

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
# SESSION UTILITIES
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


# =============================================================================
# LET THEM COOK - MAIN CLASS
# =============================================================================

class LetThemCook:
    """
    Autonomous Claude + Gemini collaboration.

    Gemini (cook) drives Claude through tasks, or watches and chimes in.
    User can interrupt and take over anytime.
    """

    def __init__(
        self,
        task: str = None,
        watch_mode: bool = False,
        passive: bool = False,
        aggressive: bool = True,
        model: str = "sonnet",
        max_turns: int = 0,
    ):
        self.task = task
        self.watch_mode = watch_mode
        self.passive = passive
        self.aggressive = aggressive
        self.model = model
        self.max_turns = max_turns
        self.gemini = GeminiClient()
        self.conversation: List[Message] = []
        self.last_position = 0
        self.running = False
        self.session_file: Optional[Path] = None

    # -------------------------------------------------------------------------
    # Streaming Output
    # -------------------------------------------------------------------------

    def _print_stream_event(self, line: str):
        """Parse and print a stream-json event with colors"""
        try:
            data = json.loads(line)
            event_type = data.get("type", "unknown")

            if event_type == "system":
                subtype = data.get("subtype", "")
                if subtype == "init":
                    model = data.get("model", "unknown")
                    print(f"{C.DIM}[init] model={model}{C.RESET}", flush=True)

            elif event_type == "assistant":
                msg = data.get("message", {})
                content_blocks = msg.get("content", [])
                for block in content_blocks:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            print(f"{C.CLAUDE}{C.BOLD}[claude]{C.RESET} {C.CLAUDE}{text}{C.RESET}", flush=True)
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "unknown")
                            tool_input = block.get("input", {})
                            input_preview = json.dumps(tool_input)[:150]
                            print(f"{C.TOOL}[tool] {C.BOLD}{tool_name}{C.RESET}{C.TOOL}: {input_preview}{C.RESET}", flush=True)

            elif event_type == "tool_result":
                content = data.get("content", "")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")[:300]
                            print(f"{C.RESULT}[result] {text}...{C.RESET}", flush=True)
                elif isinstance(content, str):
                    print(f"{C.RESULT}[result] {content[:300]}...{C.RESET}", flush=True)

            elif event_type == "result":
                subtype = data.get("subtype", "")
                cost = data.get("total_cost_usd", 0)
                duration = data.get("duration_ms", 0)
                color = C.SUCCESS if subtype == "success" else C.ERROR
                print(f"{color}[done] {subtype} | ${cost:.4f} | {duration}ms{C.RESET}", flush=True)

            elif event_type == "error":
                msg = data.get('error', {}).get('message', 'Unknown')
                print(f"{C.ERROR}[error] {msg}{C.RESET}", flush=True)

        except json.JSONDecodeError:
            if line.strip():
                print(f"{C.DIM}[raw] {line[:200]}{C.RESET}", flush=True)

    # -------------------------------------------------------------------------
    # Send to Claude (Drive Mode)
    # -------------------------------------------------------------------------

    async def send_to_claude(self, message: str, continue_session: bool = True) -> str:
        """Send a message to Claude Code and stream everything"""
        cmd = [
            CLAUDE_BIN,
            "-p",
            "--model", self.model,
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--verbose",
        ]

        if continue_session:
            cmd.append("--continue")

        cmd.append(message)

        print(f"\n{C.DIM}{'─'*60}{C.RESET}", flush=True)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            return f"[ERROR] Failed to start Claude: {e}"

        full_response = ""
        buffer = ""

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(256),
                        timeout=0.3
                    )
                    if chunk:
                        buffer += chunk.decode('utf-8', errors='replace')

                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            if line.strip():
                                self._print_stream_event(line)
                                try:
                                    data = json.loads(line)
                                    if data.get("type") == "assistant":
                                        msg = data.get("message", {})
                                        for block in msg.get("content", []):
                                            if isinstance(block, dict) and block.get("type") == "text":
                                                full_response += block.get("text", "") + "\n"
                                    elif data.get("type") == "result":
                                        result = data.get("result", "")
                                        if result and not full_response:
                                            full_response = result
                                except:
                                    pass

                    elif process.returncode is not None:
                        break
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

        except asyncio.CancelledError:
            process.kill()
            print("\n[interrupted]")
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            process.kill()
            print("\n[interrupted]")
            raise

        await process.wait()
        print(f"{C.DIM}{'─'*60}{C.RESET}\n", flush=True)

        response = full_response.strip() if full_response else "[no text response]"

        # Also read from JSONL for complete response
        session_file = get_latest_session_file()
        if session_file:
            self.session_file = session_file
            try:
                with open(session_file) as f:
                    for line in f:
                        pass  # Go to last line
                    f.seek(0)
                    lines = f.readlines()
                    if lines:
                        last_msg = parse_session_line(lines[-1])
                        if last_msg and last_msg.role == "assistant":
                            if len(last_msg.content) > len(response):
                                response = last_msg.content
            except:
                pass

        # Store in conversation
        self.conversation.append(Message(
            role="user", content=message, timestamp=datetime.now().isoformat()
        ))
        self.conversation.append(Message(
            role="assistant", content=response, timestamp=datetime.now().isoformat()
        ))

        return response

    # -------------------------------------------------------------------------
    # Gemini Decision Making
    # -------------------------------------------------------------------------

    def should_continue(self, claude_response: str) -> Optional[str]:
        """Ask Gemini if/what to send next to Claude"""
        if not self.gemini.available:
            return None

        original_task = self.task or (
            self.conversation[0].content if self.conversation else "unknown"
        )

        recent = self.conversation[-6:]
        context = "\n".join([
            f"{m.role.upper()}: {m.content[:500]}"
            for m in recent
        ])

        aggressive_note = """
IMPORTANT: This is an OPEN-ENDED, ITERATIVE task. Push for CONTINUOUS improvement.
Do NOT say [DONE] unless Claude explicitly cannot continue or needs specific user input.
Always push for the NEXT improvement, NEXT implementation, NEXT iteration.
Ask Claude to IMPLEMENT changes, not just explain them.
""" if self.aggressive else ""

        prompt = f"""You are the cook in "Let Them Cook" - driving Claude Code through tasks.

ORIGINAL TASK: {original_task}
{aggressive_note}
Claude's latest response:
---
{claude_response[:2000]}
---

Recent conversation:
{context}

What should you tell Claude next?

Rules:
1. If Claude says it CANNOT continue or needs specific user input: Output [DONE]
2. Otherwise: Output your next instruction to push the task forward
3. Be specific and actionable
4. Ask for implementations, not explanations
5. Push for the next step/improvement

Your response (next instruction, or [DONE]):"""

        response = self.gemini.analyze(prompt, max_tokens=500)

        if "[DONE]" in response or not response:
            return None

        return response.strip()

    def should_chime_in(self, latest_message: Message) -> Optional[str]:
        """Ask Gemini if we should chime in (watch mode)"""
        if self.passive or not self.gemini.available:
            return None

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

    # -------------------------------------------------------------------------
    # Drive Mode (Autonomous)
    # -------------------------------------------------------------------------

    async def run_drive_mode(self, initial_task: str):
        """Drive Claude through a task autonomously"""
        print(f"\n{C.CYAN}{'═' * 60}")
        print(f"🍳 LET THEM COOK - Drive Mode")
        print(f"{'═' * 60}{C.RESET}")
        print(f"{C.INFO}Claude: {C.CLAUDE}{self.model}{C.RESET} {C.INFO}| Gemini: {C.COOK}{self.gemini.model_name if self.gemini.available else 'off'}{C.RESET}")
        max_str = "unlimited" if self.max_turns == 0 else str(self.max_turns)
        print(f"{C.INFO}Max turns: {max_str} | Aggressive: {self.aggressive}{C.RESET}")
        print(f"\n{C.DIM}Press Ctrl+C to take over{C.RESET}")
        print(f"{C.CYAN}{'═' * 60}{C.RESET}\n")

        self.running = True
        self.task = initial_task

        # Send initial task
        print(f"{C.COOK}{C.BOLD}[cook]{C.RESET} {C.COOK}{initial_task}{C.RESET}\n")

        try:
            response = await self.send_to_claude(initial_task, continue_session=False)
        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}[interrupted] Exiting.{C.RESET}")
            return

        # Autonomous loop
        turn = 0
        while self.running and (self.max_turns == 0 or turn < self.max_turns):
            turn += 1

            try:
                next_message = self.should_continue(response)

                if not next_message:
                    print(f"\n{C.COOK}[cook]{C.RESET} {C.INFO}Task complete or needs user input.{C.RESET}")
                    await self.interactive_mode(response)
                    return

                print(f"\n{C.COOK}{C.BOLD}[cook:auto]{C.RESET} {C.COOK}{next_message}{C.RESET}\n")

                await asyncio.sleep(2)
                response = await self.send_to_claude(next_message)

            except KeyboardInterrupt:
                print(f"\n\n{C.YELLOW}[interrupted] Switching to interactive mode...{C.RESET}")
                await self.interactive_mode(response)
                return

        print(f"\n{C.INFO}[loop] Finished after {turn} turns{C.RESET}")

    # -------------------------------------------------------------------------
    # Watch Mode (Tail Session)
    # -------------------------------------------------------------------------

    async def run_watch_mode(self):
        """Watch existing Claude session and chime in when needed"""
        print(f"\n{C.CYAN}{'═' * 60}")
        print(f"🍳 LET THEM COOK - Watch Mode")
        print(f"{'═' * 60}{C.RESET}")
        print(f"{C.INFO}Mode: {'Passive (watch only)' if self.passive else 'Active (will chime in)'}{C.RESET}")
        print(f"{C.INFO}Gemini: {C.COOK}{self.gemini.model_name if self.gemini.available else 'off'}{C.RESET}")
        print(f"\n{C.DIM}Press Ctrl+C to stop{C.RESET}")
        print(f"{C.CYAN}{'═' * 60}{C.RESET}\n")

        self.running = True

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
                        await self.handle_watch_message(msg)

                await asyncio.sleep(0.5)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"{C.ERROR}[watcher:error] {e}{C.RESET}")
                await asyncio.sleep(1)

        print(f"\n{C.YELLOW}[stopped]{C.RESET}")

    async def handle_watch_message(self, msg: Message):
        """Handle a new message in watch mode"""
        if msg.role == "user":
            print(f"{C.GREEN}[user]{C.RESET} {msg.content[:100]}{'...' if len(msg.content) > 100 else ''}")

        elif msg.role == "assistant":
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
                    await asyncio.sleep(2)
                    await self.send_chime(chime)

    async def send_chime(self, message: str):
        """Send a chime-in message to Claude (watch mode)"""
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

        await process.communicate()
        print(f"{C.DIM}[sent - Claude will respond in session]{C.RESET}\n")

    # -------------------------------------------------------------------------
    # Interactive Mode
    # -------------------------------------------------------------------------

    async def interactive_mode(self, last_response: str = ""):
        """Interactive mode - user controls, can switch back to auto"""
        print(f"\n{C.GREEN}{'─' * 40}")
        print(f"INTERACTIVE MODE")
        print(f"{C.DIM}/auto  - Resume autonomous mode")
        print(f"/quit  - Exit{C.RESET}")
        print(f"{C.GREEN}{'─' * 40}{C.RESET}\n")

        loop = asyncio.get_event_loop()

        while True:
            try:
                user_input = await loop.run_in_executor(
                    None, lambda: input(f"{C.GREEN}[you]{C.RESET} ")
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input == "/quit":
                    print(f"{C.DIM}[goodbye]{C.RESET}")
                    break

                if user_input == "/auto":
                    print(f"{C.COOK}[resuming autonomous mode...]{C.RESET}")
                    await self.continue_autonomous(last_response)
                    return

                response = await self.send_to_claude(user_input)
                last_response = response

            except KeyboardInterrupt:
                print(f"\n{C.DIM}[exiting]{C.RESET}")
                break
            except EOFError:
                break

    async def continue_autonomous(self, last_response: str):
        """Continue autonomous from current state"""
        turn = 0
        while self.max_turns == 0 or turn < self.max_turns:
            turn += 1

            try:
                next_msg = self.should_continue(last_response)

                if not next_msg:
                    print(f"{C.COOK}[cook]{C.RESET} {C.INFO}Done - returning to interactive{C.RESET}")
                    await self.interactive_mode(last_response)
                    return

                print(f"\n{C.COOK}{C.BOLD}[cook:auto]{C.RESET} {C.COOK}{next_msg}{C.RESET}\n")
                await asyncio.sleep(2)

                last_response = await self.send_to_claude(next_msg)

            except KeyboardInterrupt:
                print(f"\n{C.YELLOW}[interrupted]{C.RESET}")
                await self.interactive_mode(last_response)
                return


# =============================================================================
# MAIN
# =============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Let Them Cook - Claude + Gemini Collaboration")
    parser.add_argument("task", nargs="?", help="Task to drive Claude through")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Watch mode - tail existing session")
    parser.add_argument("--passive", "-p", action="store_true",
                        help="Passive mode - watch only, don't intervene")
    parser.add_argument("--no-aggressive", action="store_true",
                        help="Less aggressive - only act when necessary")
    parser.add_argument("-m", "--model", default="sonnet",
                        help="Claude model to use")
    parser.add_argument("--max-turns", type=int, default=0,
                        help="Max turns, 0 = unlimited")

    args = parser.parse_args()

    if not os.path.exists(CLAUDE_BIN):
        print(f"{C.ERROR}[!] Claude Code not found{C.RESET}")
        sys.exit(1)

    cook = LetThemCook(
        task=args.task,
        watch_mode=args.watch,
        passive=args.passive,
        aggressive=not args.no_aggressive,
        model=args.model,
        max_turns=args.max_turns,
    )

    try:
        if args.watch or args.passive:
            await cook.run_watch_mode()
        elif args.task:
            await cook.run_drive_mode(args.task)
        else:
            # No task - start interactive
            print(f"\n{C.CYAN}{'═' * 60}")
            print(f"🍳 LET THEM COOK - Interactive Mode")
            print(f"{'═' * 60}{C.RESET}")
            print(f"{C.INFO}Claude: {C.CLAUDE}{cook.model}{C.RESET}")
            print(f"{C.DIM}/auto - Let cook take over | /quit - Exit{C.RESET}")
            print(f"{C.CYAN}{'═' * 60}{C.RESET}\n")
            await cook.interactive_mode()

    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[stopped]{C.RESET}")


if __name__ == "__main__":
    asyncio.run(main())
