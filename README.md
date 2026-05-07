# todotxt-web

A Flask web application for managing todo.txt files with user authentication, a terminal-style UI, a REST API, a CLI client, and an MCP server for Claude integration.

## Components

| Path | Description |
|------|-------------|
| `app.py` | Flask web app and REST API |
| `cli/todo.py` | Full todo.txt-compatible CLI client |
| `mcp/server.py` | MCP server for Claude |

---

## Web App

### Requirements

- Python 3.9+

### Installation

```bash
git clone https://github.com/waffle2k/todotxt-web.git
cd todotxt-web
pip install -r requirements.txt
```

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `please-change-this-secret-key-in-production` |
| `TODO_FILES_DIR` | Directory for per-user todo.txt files | current directory |
| `FLASK_DEBUG` | Enable debug mode | `False` |

### Running

```bash
export SECRET_KEY=your-secret-key
export TODO_FILES_DIR=/var/lib/todotxt
python app.py
```

For production use gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Docker

```bash
# Quick start
docker-compose up -d

# Production (set SECRET_KEY first)
export SECRET_KEY=your-very-secure-random-key
docker-compose -f docker-compose.prod.yml up -d

# Development (live reload)
docker-compose -f docker-compose.dev.yml up -d
```

The app listens on port `5001` by default when using docker-compose.

### First use

1. Open `http://localhost:5001` (or `http://localhost:5000` if running directly)
2. Register an account
3. Start adding tasks

---

## API

Authentication uses session cookies — log in via `POST /login` first.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /login` | POST | Log in; form fields: `username`, `password`, `remember` |
| `GET /api/search` | GET | Search/filter tasks |
| `POST /add` | POST | Add a task |
| `GET /complete/<id>` | GET | Toggle task completion |
| `POST /edit/<id>` | POST | Edit a task |
| `GET /delete/<id>` | GET | Delete a task |

### Search parameters (`GET /api/search`)

| Parameter | Values |
|-----------|--------|
| `q` | Free-text search |
| `priority` | `all`, `A`, `B`, `C`, `none` |
| `project` | Project name or `all` |
| `context` | Context name or `all` |
| `completed` | `all`, `completed`, `incomplete` |

### Task object

```json
{
  "id": 1,
  "raw_line": "(A) 2025-01-01 Buy groceries +errands @home",
  "description": "Buy groceries",
  "priority": "A",
  "completed": false,
  "projects": ["errands"],
  "contexts": ["home"],
  "creation_date": "2025-01-01",
  "completion_date": null
}
```

---

## CLI

A full todo.txt-compatible CLI that talks to the web API. Compatible with standard `todo.sh` command names.

### Installation

```bash
pip install -r cli/requirements.txt

# Optional: install as a command
cp cli/todo.py ~/bin/todo
chmod +x ~/bin/todo
```

### Configuration

```bash
export TODO_URL=http://localhost:5000    # or your hosted URL
export TODO_USER=youruser
export TODO_PASS=yourpassword
```

### Usage

```bash
# List incomplete tasks
todo ls

# List all tasks including completed
todo lsa

# Add a task
todo add "(A) Fix the thing +homelab @computer"

# Add with priority shorthand
todo add Buy milk +errands @home
todo pri 5 A

# Mark done
todo do 3

# Mark undone
todo undone 3

# Edit a task
todo replace 4 "Updated task description +project @context"

# Append text to a task
todo append 4 "and more details"

# Set priority
todo pri 2 B

# Remove priority
todo depri 2

# Delete a task
todo del 7

# Filter by project or context
todo ls +homelab
todo ls @computer

# List projects / contexts
todo lsprj
todo lsc

# List by priority
todo lsp A
todo lsp A-C

# Show counts
todo report
```

### Flags

| Flag | Description |
|------|-------------|
| `-p` | Plain output (no color) |
| `-c` | Force color output |
| `-v` | Verbose output |
| `-f` | Force (skip confirmation prompts) |
| `-t` | Prepend today's date when adding tasks |

---

## MCP Server

Exposes todo task management as tools for Claude. Once configured, Claude can list, add, complete, edit, and delete tasks on your behalf.

### Installation

```bash
pip install -r mcp/requirements.txt
```

### Configuration

```bash
export TODOTXT_WEB_URL=http://localhost:5000
export TODOTXT_USER=youruser
export TODOTXT_PASS=yourpassword
```

### Running

```bash
python mcp/server.py
```

### Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "todotxt": {
      "command": "python",
      "args": ["/path/to/todotxt-web/mcp/server.py"],
      "env": {
        "TODOTXT_WEB_URL": "http://localhost:5000",
        "TODOTXT_USER": "youruser",
        "TODOTXT_PASS": "yourpassword"
      }
    }
  }
}
```

### Claude Code (CLI) configuration

Add to `~/.claude/settings.json` or your project's `.claude/settings.json`:

```json
{
  "mcpServers": {
    "todotxt": {
      "command": "python",
      "args": ["/path/to/todotxt-web/mcp/server.py"],
      "env": {
        "TODOTXT_WEB_URL": "http://localhost:5000",
        "TODOTXT_USER": "youruser",
        "TODOTXT_PASS": "yourpassword"
      }
    }
  }
}
```

### Available tools

| Tool | Description |
|------|-------------|
| `list_tasks(search, priority, project, context, completed)` | List and filter tasks |
| `add_task(description, priority, projects, contexts)` | Add a new task |
| `complete_task(task_id)` | Mark a task as completed |
| `uncomplete_task(task_id)` | Mark a completed task as incomplete |
| `edit_task(task_id, description, priority, projects, contexts)` | Edit an existing task |
| `delete_task(task_id)` | Permanently delete a task |

---

## Todo.txt format

```
(A) 2025-01-01 High priority task +Project @context
2025-01-01 Regular task +AnotherProject @home
x 2025-01-15 2025-01-01 Completed task +Project @context
```

- `(A)`, `(B)`, `(C)` — Priority levels
- `+Project` — Project tags
- `@context` — Context tags
- `x` — Completed task marker
- Dates in `YYYY-MM-DD` format

---

## File structure

```
todotxt-web/
├── app.py              # Flask app and API routes
├── user_manager.py     # User auth and account management
├── todo_parser.py      # Todo.txt parsing
├── requirements.txt    # Web app dependencies
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── docker-compose.dev.yml
├── cli/
│   ├── todo.py         # CLI client
│   └── requirements.txt
├── mcp/
│   ├── server.py       # MCP server
│   └── requirements.txt
├── templates/          # Jinja2 HTML templates
└── static/             # CSS and JS
```
