# 🍳 Let Them Cook

An autonomous watcher that monitors Claude Code and chimes in when needed.

Like a pair programmer watching over your shoulder - it tails Claude's session in real-time and provides guidance when Claude gets stuck, makes mistakes, or could use a push in the right direction.

## How It Works

```
┌─────────────────┐
│   Claude Code   │ ◄── You (or the watcher) sends tasks
│   (Terminal)    │
└────────┬────────┘
         │
         ▼ writes to
┌─────────────────┐
│  Session JSONL  │ ◄── ~/.claude/projects/<project>/*.jsonl
└────────┬────────┘
         │
         ▼ tails
┌─────────────────┐
│  Let Them Cook  │ ──► Analyzes responses with Gemini
│   (Watcher)     │ ──► Decides if it should chime in
└────────┬────────┘ ──► Sends follow-ups via --continue
         │
         ▼
    Back to Claude
```

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/let-them-cook.git
cd let-them-cook

pip install -r requirements.txt

# Set up API key
export GOOGLE_API_KEY="your-gemini-key"

# Make executable
chmod +x let_them_cook.py
```

## Usage

### Watch Mode (most common)
```bash
# Start Claude Code in one terminal
claude

# Run the watcher in another terminal
./let_them_cook.py
```

The watcher will:
1. Find the latest Claude session
2. Tail the JSONL file in real-time
3. Analyze each Claude response
4. Chime in when it thinks guidance would help

### Start with a Task
```bash
# Start Claude with a task and watch
./let_them_cook.py --task "Build a REST API with user authentication"
```

### Passive Mode (watch only)
```bash
# Just watch, never intervene
./let_them_cook.py --passive
```

## Options

| Flag | Description |
|------|-------------|
| `--task, -t` | Start Claude with this task |
| `--passive, -p` | Watch only, don't send messages |
| `--no-aggressive` | Less proactive, only chime in when necessary |
| `-m, --model` | Claude model (default: sonnet) |

## Output Colors

- 🟣 **Purple** `[claude]` - Claude's responses
- 🟠 **Orange** `[cook]` - Watcher's messages
- 🔵 **Blue** `[tool]` - Tool calls
- 🟢 **Green** `[user]` - User messages
- ⚪ **Gray** - Info and metadata

## When Does It Chime In?

The watcher uses Gemini to decide if Claude needs help:

- **Stuck**: Claude seems confused or going in circles
- **Wrong direction**: Claude misunderstood the task
- **Errors**: Claude made a mistake that needs correction
- **Next step**: There's an obvious next action Claude should take
- **Incomplete**: The task isn't done yet

## Example Session

```
═══════════════════════════════════════════════════════════
🍳 LET THEM COOK - Autonomous Watcher
═══════════════════════════════════════════════════════════
Mode: Active (will chime in)
Model: sonnet

[watcher] Found: abc123.jsonl
[watcher] Tailing session...

[user] Build a login form with validation
[tool] Read
[claude] I'll create a login form component...
[tool] Write
[claude] Done! Created LoginForm.tsx with email/password fields.

[cook] Great start! Now add client-side validation for:
       1. Email format checking
       2. Password minimum length
       3. Show error messages inline

[tool] Edit
[claude] Added validation with inline error messages...
```

## Requirements

- Python 3.8+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Google Gemini API key

## License

MIT
