# Let Them Cook

Autonomous Claude + Gemini collaboration. Two AI agents cooking together.

- **Gemini** (the cook) drives the direction and decides next steps
- **Claude Code** executes, writes code, uses tools
- **You** can interrupt and join anytime

## How It Works

```
┌─────────────────┐
│     Gemini      │ ◄── "The Cook" - decides what to do next
│   (Director)    │
└────────┬────────┘
         │ drives
         ▼
┌─────────────────┐
│   Claude Code   │ ◄── Executes tasks, writes code, uses tools
│   (Executor)    │
└────────┬────────┘
         │ streams output
         ▼
┌─────────────────┐
│   You (Human)   │ ◄── Ctrl+C to take over anytime
└─────────────────┘
```

## Installation

```bash
git clone https://github.com/friday-james/let-them-cook.git
cd let-them-cook

pip install -r requirements.txt

# Set up API key
export GOOGLE_API_KEY="your-gemini-key"

# Make executable
chmod +x let_them_cook.py
```

## Usage

### Drive Mode (default)
Gemini actively drives Claude through tasks:

```bash
./let_them_cook.py "Build a REST API with user authentication"
```

### Relentless Mode
Never stops. Always finds more to do - tests, edge cases, optimizations, docs:

```bash
./let_them_cook.py -r "Build a CLI tool"
```

### Watch Mode
Tail an existing Claude session and chime in when needed:

```bash
# Terminal 1: run Claude Code
claude

# Terminal 2: watch and intervene
./let_them_cook.py --watch
```

### Passive Mode
Watch only, never intervene:

```bash
./let_them_cook.py --passive
```

### Interactive Mode
Start without a task, you drive:

```bash
./let_them_cook.py
```

## Interrupting & Joining

Press `Ctrl+C` anytime to take over:

```
[cook:auto] implementing auth...

^C  ← you interrupt

────────────────────────────────
YOUR TURN
/stay  - Stay in interactive mode
/quit  - Exit
────────────────────────────────

[you] focus on the login flow first

[cook] [auto-resuming...]  ← automatically continues
```

Your message is sent, then it auto-resumes. Use `/stay` to keep driving manually.

## Options

| Flag | Description |
|------|-------------|
| `task` | Task to drive Claude through |
| `-r, --relentless` | Never stop, always find more to do |
| `-w, --watch` | Watch mode - tail existing session |
| `-p, --passive` | Passive mode - watch only |
| `--no-aggressive` | Less aggressive - stop when task seems done |
| `-m, --model` | Claude model (default: sonnet) |
| `--max-turns` | Max turns, 0 = unlimited (default: 0) |

## Commands (Interactive Mode)

| Command | Description |
|---------|-------------|
| `/stay` | Stay in interactive mode (don't auto-resume) |
| `/quit` | Exit |
| `Ctrl+C` | Interrupt and take over |

## Output Colors

- **Purple** `[claude]` - Claude's responses
- **Orange** `[cook]` - Gemini's instructions
- **Blue** `[tool]` - Tool calls
- **Gray** `[result]` - Tool results
- **Green** `[you]` - Your messages
- **Green** `[done]` - Success
- **Red** `[error]` - Errors

## Example Session

```
════════════════════════════════════════════════════════════
🍳 LET THEM COOK - Relentless Mode
════════════════════════════════════════════════════════════
Claude: sonnet | Gemini: gemini-2.0-flash
Max turns: unlimited | RELENTLESS (never stops)

Press Ctrl+C to take over
════════════════════════════════════════════════════════════

[cook] Build a REST API with user authentication

────────────────────────────────────────────────────────────
[init] model=claude-sonnet-4-20250514
[claude] I'll create a REST API with user authentication...
[tool] Write: {"file_path": "/api/server.py"...}
[result] File created successfully...
[tool] Write: {"file_path": "/api/auth.py"...}
[done] success | $0.0234 | 12340ms
────────────────────────────────────────────────────────────

[cook:auto] Good start! Now add JWT token generation and password hashing...

────────────────────────────────────────────────────────────
[claude] I'll add JWT authentication with bcrypt...
[tool] Edit: {"file_path": "/api/auth.py"...}
[done] success | $0.0156 | 8420ms
────────────────────────────────────────────────────────────

[cook:auto] Now add input validation and error handling...

... continues indefinitely until Ctrl+C ...
```

## Requirements

- Python 3.8+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Google Gemini API key

## License

MIT
