#!/usr/bin/env python3
"""todo - todo.txt CLI backed by the todotxt web API"""

import http.cookiejar
import json as _json
import os
import re
import sys
import datetime
import urllib.error
import urllib.parse
import urllib.request

# ── Configuration ────────────────────────────────────────────────────────────

def _load_config():
    """Load KEY=VALUE pairs from ~/.config/todotui/config (# comments, blank lines OK)."""
    cfg = {}
    path = os.path.join(os.path.expanduser("~"), ".config", "todotui", "config")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg

_cfg = _load_config()

def _get_cfg(key):
    return os.environ.get(key) or _cfg.get(key)

BASE_URL = _get_cfg("TODO_URL")
USERNAME = _get_cfg("TODO_USER")
PASSWORD = _get_cfg("TODO_PASS")

if not BASE_URL or not USERNAME or not PASSWORD:
    missing = [k for k, v in [("TODO_URL", BASE_URL), ("TODO_USER", USERNAME), ("TODO_PASS", PASSWORD)] if not v]
    print(f"TODO: {', '.join(missing)} must be set via env var or ~/.config/todotui/config", file=sys.stderr)
    sys.exit(1)

VERSION = "1.0.0 (web-api)"

# ── ANSI colors (matching todo.sh defaults) ───────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
YELLOW  = "\033[0;33m"
GREEN   = "\033[0;32m"
CYAN    = "\033[0;36m"
WHITE   = "\033[1;37m"
GREY    = "\033[1;30m"

PRI_COLOR = {"A": YELLOW, "B": GREEN, "C": CYAN}

# ── Global flags (set by _parse_flags) ───────────────────────────────────────

g_plain      = not sys.stdout.isatty()  # -p / -c
g_verbose    = False                     # -v
g_force      = False                     # -f
g_auto_arch  = False                     # -A
g_prepend_dt = False                     # -t / -T
g_hide_proj  = False                     # -+
g_hide_ctx   = False                     # -@
g_hide_pri   = False                     # -P

# ── HTTP session ─────────────────────────────────────────────────────────────

_jar    = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_authenticated = False


class _Resp:
    """Minimal requests-compatible wrapper around a urllib response."""
    def __init__(self, status: int, url: str, body: bytes):
        self.status_code = status
        self.ok          = 200 <= status < 300
        self.url         = url
        self._body       = body

    def json(self):
        return _json.loads(self._body)

    def raise_for_status(self):
        if not self.ok:
            raise urllib.error.HTTPError(self.url, self.status_code,
                                         f"HTTP {self.status_code}", {}, None)


def _request(url: str, data=None, params=None) -> _Resp:
    if params:
        qs  = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{qs}"
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req  = urllib.request.Request(url, data=body, headers={"User-Agent": "todo-cli/1.0"})
    try:
        with _opener.open(req) as r:
            return _Resp(r.status, r.geturl(), r.read())
    except urllib.error.HTTPError as e:
        return _Resp(e.code, e.url or url, e.read() or b"")


def _login():
    global _authenticated
    r = _request(f"{BASE_URL}/login",
                 data={"username": USERNAME, "password": PASSWORD, "remember": "on"})
    _authenticated = r.ok and "/login" not in r.url
    if not _authenticated:
        _die("Login failed")


def _get(path, **kwargs):
    global _authenticated
    if not _authenticated:
        _login()
    r = _request(f"{BASE_URL}{path}", params=kwargs.get("params"))
    if "/login" in r.url:
        _login()
        r = _request(f"{BASE_URL}{path}", params=kwargs.get("params"))
    return r


def _post(path, data):
    global _authenticated
    if not _authenticated:
        _login()
    r = _request(f"{BASE_URL}{path}", data=data)
    if "/login" in r.url:
        _login()
        r = _request(f"{BASE_URL}{path}", data=data)
    return r


def _fetch(**params):
    defaults = {"q": "", "priority": "all", "project": "all",
                "context": "all", "completed": "all"}
    defaults.update(params)
    r = _get("/api/search", params=defaults)
    r.raise_for_status()
    return r.json()["tasks"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _die(msg, code=1):
    print(f"TODO: {msg}", file=sys.stderr)
    sys.exit(code)


def _color(text, code):
    return f"{code}{text}{RESET}" if not g_plain else text


def _fmt(task, w=3):
    tid = str(task["id"]).rjust(w)
    raw = _apply_visibility(task["raw_line"])
    if task["completed"]:
        return _color(f"{tid} {raw}", GREY)
    pri = task.get("priority") or ""
    code = PRI_COLOR.get(pri, "")
    return _color(f"{tid} {raw}", code) if code else f"{tid} {raw}"


def _apply_visibility(raw):
    if g_hide_proj:
        raw = re.sub(r'\s\+\S+', '', raw)
    if g_hide_ctx:
        raw = re.sub(r'\s@\S+', '', raw)
    if g_hide_pri:
        raw = re.sub(r'^\([A-Z]\) ', '', raw)
    return raw


def _get_task(tid, completed="all"):
    tasks = _fetch(completed=completed)
    return next((t for t in tasks if t["id"] == tid), None)


def _clean_desc(description):
    """Strip +proj and @ctx markers from a description string.

    The web app re-adds them from the structured projects/contexts fields,
    so sending them in both places causes duplication in raw_line.
    """
    return re.sub(r'\s*[+@]\S+', '', description).strip()


def _parse_raw(text):
    """Return (priority, description, projects, contexts) from todo.txt-style text.

    The description returned has +proj and @ctx markers stripped — the web app
    re-appends them from the separate projects/contexts fields when building raw_line.
    """
    priority = ""
    m = re.match(r'^\(([A-Z])\)\s+', text)
    if m:
        priority = m.group(1)
        text = text[m.end():]
    projects = re.findall(r'\+(\S+)', text)
    contexts = re.findall(r'@(\S+)', text)
    clean = re.sub(r'\s*[+@]\S+', '', text).strip()
    return priority, clean, projects, contexts


def _parse_pri_range(spec):
    """Turn 'A', 'ABC', or 'B-D' into a list of priority letters."""
    if not spec:
        return None
    if len(spec) == 1:
        return [spec.upper()]
    if '-' in spec and len(spec) == 3:
        a, b = spec[0].upper(), spec[2].upper()
        return [chr(c) for c in range(ord(a), ord(b) + 1)]
    return list(spec.upper())


def _filter(tasks, terms):
    """Filter tasks by terms (AND logic; prefix '-' to negate; '|' for OR in one term)."""
    if not terms:
        return tasks
    result = []
    for t in tasks:
        raw = t["raw_line"].lower()
        match = True
        for term in terms:
            if term.startswith("-") and len(term) > 1:
                if term[1:].lower() in raw:
                    match = False; break
            elif "|" in term:
                alts = [a.lower() for a in term.split("|")]
                if not any(a in raw for a in alts):
                    match = False; break
            else:
                if term.lower() not in raw:
                    match = False; break
        if match:
            result.append(t)
    return result


def _sorted_tasks(tasks):
    return sorted(tasks, key=lambda t: (t.get("priority") or "ZZ", t["id"]))


def _width(tasks):
    return len(str(max((t["id"] for t in tasks), default=0)))


def _today():
    return datetime.date.today().strftime("%Y-%m-%d")


def _confirm(prompt):
    if g_force:
        return True
    print(f"{prompt} [y/N] ", end="", flush=True)
    return sys.stdin.readline().strip().lower() == "y"


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args):
    if not args:
        _die("Usage: todo add TASK")
    text = " ".join(args)
    if g_prepend_dt and not re.match(r'^\d{4}-\d{2}-\d{2}\b', text.lstrip('(A-Z) ')):
        # Insert date after priority if present
        m = re.match(r'^(\([A-Z]\) )(.*)', text)
        text = f"{m.group(1)}{_today()} {m.group(2)}" if m else f"{_today()} {text}"
    _add_one(text)


def cmd_addm(args):
    if not args:
        _die("Usage: todo addm \"TASK1\\nTASK2\"")
    for line in " ".join(args).split("\\n"):
        line = line.strip()
        if line:
            _add_one(line)


def _add_one(text):
    priority, desc, projects, contexts = _parse_raw(text)
    r = _post("/add", {
        "description": desc,
        "priority": priority,
        "projects": ",".join(projects),
        "contexts": ",".join(contexts),
    })
    if not r.ok:
        _die(f"Error adding task (HTTP {r.status_code})")
    tasks = _fetch(completed="all")
    candidates = [t for t in tasks if desc[:20] in t["description"]]
    newest = max(candidates, key=lambda t: t["id"]) if candidates else None
    if newest:
        print(f"{newest['id']} {newest['raw_line']}")
        if g_verbose:
            total = len(_fetch(completed="incomplete"))
            print(f"TODO: {newest['id']} added. ({total} tasks in todo list)")
    else:
        print("TODO: Task added.")


def cmd_append(args):
    if len(args) < 2:
        _die("Usage: todo append NUM TEXT")
    tid = int(args[0])
    text = " ".join(args[1:])
    task = _get_task(tid)
    if not task:
        _die(f"No task {tid}.")
    _, appended_clean, new_proj, new_ctx = _parse_raw(text)
    projects = list(set((task.get("projects") or []) + new_proj))
    contexts = list(set((task.get("contexts") or []) + new_ctx))
    sep = "" if text and text[0] in ",.;:" else " "
    new_desc = _clean_desc(task["description"]) + sep + appended_clean
    r = _post(f"/edit/{tid}", {
        "description": new_desc,
        "priority": task.get("priority") or "",
        "projects": ",".join(projects),
        "contexts": ",".join(contexts),
    })
    if r.ok:
        updated = _get_task(tid)
        if updated:
            print(f"{tid} {updated['raw_line']}")
        if g_verbose:
            print(f"TODO: {tid} appended.")
    else:
        _die(f"Error appending to task {tid} (HTTP {r.status_code})")


def cmd_archive(args):
    tasks = _fetch(completed="completed")
    if not tasks:
        print("TODO: No completed tasks to archive.")
        return
    print(f"TODO: {len(tasks)} completed task(s) already marked done.")
    if g_verbose:
        for t in tasks:
            print(f"  {t['id']} {t['raw_line']}")


def cmd_deduplicate(args):
    tasks = _fetch(completed="all")
    seen = {}
    deleted = 0
    for t in tasks:
        key = t["raw_line"].strip()
        if key in seen:
            r = _get(f"/delete/{t['id']}")
            if r.ok:
                deleted += 1
                if g_verbose:
                    print(f"TODO: Deleted duplicate: {t['id']} {t['raw_line']}")
        else:
            seen[key] = t["id"]
    print(f"TODO: {deleted} duplicate(s) removed.")


def cmd_del(args):
    if not args:
        _die("Usage: todo del NUM [TERM]")
    tid = int(args[0])
    term = " ".join(args[1:]) if len(args) > 1 else None
    task = _get_task(tid)
    if not task:
        _die(f"No task {tid}.")
    if term:
        # Remove TERM from the task description rather than deleting the task
        if term not in task["description"]:
            _die(f"'{term}' not found in task {tid}.")
        raw_minus_term = task["description"].replace(term, "").strip()
        raw_minus_term = re.sub(r'\s+', ' ', raw_minus_term)
        _, _, projects, contexts = _parse_raw(raw_minus_term)
        new_desc = _clean_desc(raw_minus_term)
        r = _post(f"/edit/{tid}", {
            "description": new_desc,
            "priority": task.get("priority") or "",
            "projects": ",".join(projects),
            "contexts": ",".join(contexts),
        })
        if r.ok:
            updated = _get_task(tid)
            if updated:
                print(f"{tid} {updated['raw_line']}")
            if g_verbose:
                print(f"TODO: {tid} updated.")
        else:
            _die(f"Error editing task {tid} (HTTP {r.status_code})")
    else:
        if not _confirm(f"Delete '{task['raw_line']}'?"):
            print("TODO: No tasks were deleted."); return
        r = _get(f"/delete/{tid}")
        if r.ok:
            if g_verbose:
                print(f"TODO: {tid} deleted.")
            else:
                print(f"TODO: {tid} deleted.")
        else:
            _die(f"Error deleting task {tid} (HTTP {r.status_code})")


def cmd_depri(args):
    if not args:
        _die("Usage: todo depri NUM [NUM ...]")
    for num in _expand_nums(args):
        task = _get_task(num)
        if not task:
            print(f"TODO: No task {num}.", file=sys.stderr); continue
        if not task.get("priority"):
            print(f"TODO: {num} is not prioritized."); continue
        r = _post(f"/edit/{num}", {
            "description": _clean_desc(task["description"]),
            "priority": "",
            "projects": ",".join(task.get("projects") or []),
            "contexts": ",".join(task.get("contexts") or []),
        })
        if r.ok:
            updated = _get_task(num)
            if updated:
                print(f"{num} {updated['raw_line']}")
            if g_verbose:
                print(f"TODO: {num} deprioritized.")
        else:
            print(f"TODO: Error deprioritizing {num} (HTTP {r.status_code})", file=sys.stderr)


def cmd_do(args):
    if not args:
        _die("Usage: todo do NUM [NUM ...]")
    for num in _expand_nums(args):
        task = _get_task(num, completed="incomplete")
        if not task:
            print(f"TODO: No incomplete task {num}.", file=sys.stderr); continue
        r = _get(f"/complete/{num}")
        if r.ok:
            print(f"{num} {task['raw_line']}")
            if g_verbose:
                done = len(_fetch(completed="completed"))
                print(f"TODO: {num} marked as done. ({done} done.)")
            if g_auto_arch and g_verbose:
                print("TODO: Archived.")
        else:
            print(f"TODO: Error completing {num} (HTTP {r.status_code})", file=sys.stderr)


def cmd_help(args):
    if args:
        _die(f"No specific help for '{args[0]}' — run 'todo help' for all commands.")
    print(USAGE)


def cmd_shorthelp(args):
    print(SHORTHELP)


def cmd_list(args, completed="incomplete"):
    tasks = _filter(_fetch(completed=completed), args)
    tasks = _sorted_tasks(tasks)
    if not tasks:
        total = len(_fetch(completed="incomplete"))
        print(f"TODO: 0 of {total} tasks shown")
        return
    w = _width(tasks)
    for t in tasks:
        print(_fmt(t, w))
    total = len(_fetch(completed="incomplete"))
    print(f"--\nTODO: {len(tasks)} of {total} tasks shown")


def cmd_listall(args):
    cmd_list(args, completed="all")


def cmd_listfile(args):
    # Single-file backend: treat as listall with optional filter
    cmd_list(args[1:] if args else [], completed="all")


def cmd_listcon(args):
    tasks = _filter(_fetch(completed="all"), args)
    ctxs = sorted(set(c for t in tasks for c in (t.get("contexts") or [])))
    for c in ctxs:
        print(f"@{c}")


def cmd_listproj(args):
    tasks = _filter(_fetch(completed="all"), args)
    projs = sorted(set(p for t in tasks for p in (t.get("projects") or [])))
    for p in projs:
        print(f"+{p}")


def cmd_listpri(args):
    terms = []
    pri_spec = None
    if args and re.match(r'^[A-Z]([A-Z]|-[A-Z])*$', args[0].upper()):
        pri_spec = args[0].upper()
        terms = args[1:]
    else:
        terms = args
    allowed = _parse_pri_range(pri_spec)
    tasks = _fetch(completed="incomplete")
    if allowed:
        tasks = [t for t in tasks if t.get("priority") in allowed]
    else:
        tasks = [t for t in tasks if t.get("priority")]
    tasks = _filter(tasks, terms)
    tasks = _sorted_tasks(tasks)
    if not tasks:
        print("TODO: 0 tasks shown"); return
    w = _width(tasks)
    for t in tasks:
        print(_fmt(t, w))


def cmd_listaddons(args):
    print("TODO: No add-on actions available (web-api backend).")


def cmd_move(args):
    print("TODO: move/mv not supported (single-file backend).", file=sys.stderr)
    sys.exit(1)


def cmd_prepend(args):
    if len(args) < 2:
        _die("Usage: todo prepend NUM TEXT")
    tid = int(args[0])
    text = " ".join(args[1:])
    task = _get_task(tid)
    if not task:
        _die(f"No task {tid}.")
    _, prepend_clean, new_proj, new_ctx = _parse_raw(text)
    projects = list(set((task.get("projects") or []) + new_proj))
    contexts = list(set((task.get("contexts") or []) + new_ctx))
    new_desc = prepend_clean + " " + _clean_desc(task["description"])
    r = _post(f"/edit/{tid}", {
        "description": new_desc,
        "priority": task.get("priority") or "",
        "projects": ",".join(projects),
        "contexts": ",".join(contexts),
    })
    if r.ok:
        updated = _get_task(tid)
        if updated:
            print(f"{tid} {updated['raw_line']}")
        if g_verbose:
            print(f"TODO: {tid} prepended.")
    else:
        _die(f"Error prepending to task {tid} (HTTP {r.status_code})")


def cmd_pri(args):
    if len(args) < 2:
        _die("Usage: todo pri NUM PRIORITY [NUM PRIORITY ...]")
    pairs = list(zip(args[::2], args[1::2]))
    for num_str, pri in pairs:
        tid = int(num_str)
        pri = pri.upper()
        if not re.match(r'^[A-Z]$', pri):
            print(f"TODO: Priority must be A-Z.", file=sys.stderr); continue
        task = _get_task(tid)
        if not task:
            print(f"TODO: No task {tid}.", file=sys.stderr); continue
        r = _post(f"/edit/{tid}", {
            "description": _clean_desc(task["description"]),
            "priority": pri,
            "projects": ",".join(task.get("projects") or []),
            "contexts": ",".join(task.get("contexts") or []),
        })
        if r.ok:
            updated = _get_task(tid)
            if updated:
                print(f"{tid} {updated['raw_line']}")
            if g_verbose:
                print(f"TODO: {tid} prioritized ({pri}).")
        else:
            print(f"TODO: Error prioritizing {tid} (HTTP {r.status_code})", file=sys.stderr)


def cmd_replace(args):
    if len(args) < 2:
        _die("Usage: todo replace NUM TASK")
    tid = int(args[0])
    text = " ".join(args[1:])
    task = _get_task(tid)
    if not task:
        _die(f"No task {tid}.")
    priority, desc, projects, contexts = _parse_raw(text)
    r = _post(f"/edit/{tid}", {
        "description": desc,
        "priority": priority,
        "projects": ",".join(projects),
        "contexts": ",".join(contexts),
    })
    if r.ok:
        updated = _get_task(tid)
        if updated:
            print(f"{tid} {updated['raw_line']}")
        if g_verbose:
            print(f"TODO: {tid} replaced.")
    else:
        _die(f"Error replacing task {tid} (HTTP {r.status_code})")


def cmd_report(args):
    all_tasks = _fetch(completed="all")
    done    = sum(1 for t in all_tasks if t["completed"])
    pending = len(all_tasks) - done
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"{ts} {pending} {done}")
    print(f"TODO: {pending} open, {done} done — report generated.")


def cmd_undone(args):
    if not args:
        _die("Usage: todo undone NUM")
    for num in _expand_nums(args):
        task = _get_task(num, completed="completed")
        if not task:
            print(f"TODO: No completed task {num}.", file=sys.stderr); continue
        r = _get(f"/complete/{num}")
        if r.ok:
            updated = _get_task(num)
            if updated:
                print(f"{num} {updated['raw_line']}")
            if g_verbose:
                print(f"TODO: {num} marked as incomplete.")
        else:
            print(f"TODO: Error undoing {num} (HTTP {r.status_code})", file=sys.stderr)


def cmd_version(args):
    print(f"todo version {VERSION}")


def cmd_command(args):
    if not args:
        _die("Usage: todo command ACTION [ARGS...]")
    fn = COMMANDS.get(args[0])
    if not fn:
        _die(f"Unknown built-in action: {args[0]}")
    fn(args[1:])


_COMPLETION_BASH = r'''\
# todo bash completion + fzf helpers
# Source this file or place it in ~/.bash_completion.d/todo

# ── Tab completion (subcommands + task IDs) ───────────────────────────────────
_todo() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local cmds="add a addm append app archive command deduplicate del rm depri dp do d done help list ls listall lsa listcon lsc listproj lsprj listpri lsp listfile lf move mv prepend prep pri p replace report shorthelp undone u completion"
    local id_cmds="del rm do d done depri dp undone u pri p append app prepend prep replace"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
        return
    fi

    local subcmd="${COMP_WORDS[1]}"
    if [[ " $id_cmds " == *" $subcmd "* ]]; then
        local ids
        ids=$(todo ls 2>/dev/null | awk '{print $1}')
        COMPREPLY=($(compgen -W "$ids" -- "$cur"))
    fi
}
complete -F _todo todo

# ── fzf helpers (only defined when fzf is available) ─────────────────────────
if command -v fzf &>/dev/null; then
    _todo_fzf_pick() {
        todo ls 2>/dev/null \
            | fzf --height=40% --reverse --prompt="todo> " \
                  --preview="echo {}" --preview-window=up:2 \
            | awk "{print \$1}"
    }

    todo-do()     { local id; id=$(_todo_fzf_pick) && [[ -n "$id" ]] && todo do  "$id"; }
    todo-del()    { local id; id=$(_todo_fzf_pick) && [[ -n "$id" ]] && todo del -f "$id"; }
    todo-pri()    { local id; id=$(_todo_fzf_pick) && [[ -n "$id" ]] && todo pri "$id" "${1:-A}"; }
    todo-edit()   { local id; id=$(_todo_fzf_pick) && [[ -n "$id" ]] && todo replace "$id"; }
    todo-undone() { local id; id=$(_todo_fzf_pick) && [[ -n "$id" ]] && todo undone "$id"; }
fi
'''

_COMPLETION_ZSH = r'''\
# todo zsh completion + fzf helpers
# Usage:
#   eval "$(todo completion zsh)"          # add to ~/.zshrc
#   todo completion zsh > ~/.zfunc/_todo   # or install as a function file

# ── Tab completion (subcommands + task IDs) ───────────────────────────────────
_todo() {
    local -a cmds id_cmds
    cmds=(
        add a addm 'append:append text to a task' app archive command deduplicate
        'del:delete a task' rm 'depri:remove priority' dp
        'do:mark done' d done help 'list:list tasks' ls listall lsa
        listcon lsc listproj lsprj listpri lsp listfile lf
        move mv prepend prep 'pri:set priority' p replace report shorthelp
        'undone:mark incomplete' u completion
    )
    id_cmds=(del rm do d done depri dp undone u pri p append app prepend prep replace)

    if (( CURRENT == 2 )); then
        _describe 'subcommand' cmds
        return
    fi

    local subcmd="${words[2]}"
    if (( ${id_cmds[(I)$subcmd]} )); then
        local -a ids
        ids=(${(f)"$(todo ls 2>/dev/null | awk '{print $1}')"})
        _describe 'task id' ids
    fi
}
compdef _todo todo

# ── fzf helpers (only defined when fzf is available) ─────────────────────────
if command -v fzf &>/dev/null; then
    _todo_fzf_pick() {
        todo ls 2>/dev/null \
            | fzf --height=40% --reverse --prompt="todo> " \
                  --preview="echo {}" --preview-window=up:2 \
            | awk "{print \$1}"
    }

    todo-do()     { local id=$(_todo_fzf_pick); [[ -n "$id" ]] && todo do  "$id"; }
    todo-del()    { local id=$(_todo_fzf_pick); [[ -n "$id" ]] && todo del -f "$id"; }
    todo-pri()    { local id=$(_todo_fzf_pick); [[ -n "$id" ]] && todo pri "$id" "${1:-A}"; }
    todo-edit()   { local id=$(_todo_fzf_pick); [[ -n "$id" ]] && todo replace "$id"; }
    todo-undone() { local id=$(_todo_fzf_pick); [[ -n "$id" ]] && todo undone "$id"; }
fi
'''


def cmd_completion(args):
    shell = args[0] if args else ""
    if shell == "bash":
        print(_COMPLETION_BASH, end="")
    elif shell == "zsh":
        print(_COMPLETION_ZSH, end="")
    else:
        print("Usage: todo completion <bash|zsh>", file=sys.stderr)
        print("\nInstall:")
        print("  bash:  todo completion bash >> ~/.bashrc && source ~/.bashrc")
        print("  zsh:   todo completion zsh  >> ~/.zshrc  && source ~/.zshrc")
        sys.exit(1)


# ── Utility ───────────────────────────────────────────────────────────────────

def _expand_nums(args):
    """Accept '1,2,3' or '1 2 3' and return list of ints."""
    nums = []
    for a in args:
        for part in a.split(","):
            part = part.strip()
            if part.isdigit():
                nums.append(int(part))
    return nums


# ── Flag parsing ──────────────────────────────────────────────────────────────

def _parse_flags(argv):
    global g_plain, g_verbose, g_force, g_auto_arch, g_prepend_dt
    global g_hide_proj, g_hide_ctx, g_hide_pri
    i = 0
    rest = []
    while i < len(argv):
        a = argv[i]
        if a == "-p":
            g_plain = True
        elif a == "-c":
            g_plain = False
        elif a in ("-v", "-vv"):
            g_verbose = True
        elif a == "-f":
            g_force = True
        elif a == "-A":
            g_auto_arch = True
        elif a == "-a":
            g_auto_arch = False
        elif a == "-t":
            g_prepend_dt = True
        elif a == "-T":
            g_prepend_dt = False
        elif a == "-+":
            g_hide_proj = not g_hide_proj
        elif a == "-@":
            g_hide_ctx = not g_hide_ctx
        elif a == "-P":
            g_hide_pri = not g_hide_pri
        elif a in ("-V",):
            cmd_version([])
            sys.exit(0)
        elif a in ("-h",):
            print(SHORTHELP); sys.exit(0)
        elif a == "-d":
            i += 1  # config file — ignored (use env vars instead)
        elif a == "-n" or a == "-N" or a == "-x":
            pass  # line-number / filter options not applicable
        elif a.startswith("-") and len(a) > 1 and a[1:].isalpha():
            print(f"TODO: Unknown flag {a}", file=sys.stderr)
        else:
            rest.append(a)
        i += 1
    return rest


# ── Help text ─────────────────────────────────────────────────────────────────

SHORTHELP = """\
  add|a TASK          add TASK to todo list
  addm TASKS          add multiple newline-separated tasks
  append|app N TEXT   append TEXT to task N
  archive             show archived (done) task count
  command CMD [ARGS]  run builtin CMD only
  deduplicate         remove duplicate tasks
  del|rm N [TERM]     delete task N, or remove TERM from task N
  depri|dp N [N...]   remove priority from task(s)
  do|d N [N...]       mark task(s) as done
  help                show this help
  list|ls [TERM...]   list incomplete tasks, filtered by TERM(s)
  listall|lsa [TERM]  list all tasks including done
  listcon|lsc [TERM]  list @contexts
  listproj|lsprj [T]  list +projects
  listpri|lsp [PRI]   list tasks with priority (A, B-D, ABC…)
  listfile|lf [TERM]  list all tasks (single-file backend)
  listaddons          list add-on actions
  move|mv N DEST      not supported (single-file backend)
  prepend|prep N TEXT prepend TEXT to task N
  pri|p N PRI [...]   set priority (A-Z) for task(s)
  replace N TASK      replace task N entirely
  report              show open/done counts
  shorthelp           show this summary
  undone|u N [N...]   mark done task(s) as incomplete
  completion bash|zsh print shell completion script

Flags: -f (force) -p (plain) -c (color) -v (verbose) -A (auto-archive)
       -t (prepend date) -+ (hide projects) -@ (hide contexts) -P (hide priority)"""

USAGE = f"""\
  Usage: todo [-flags] COMMAND [ARGS...]

{SHORTHELP}

  Environment / ~/.config/todotui/config:
    TODO_URL   Base URL  (required)
    TODO_USER  Username  (required)
    TODO_PASS  Password  (required)

  Filter syntax:
    TERM       match tasks containing TERM (case-insensitive)
    -TERM      exclude tasks containing TERM
    A|B        match tasks containing A or B"""

COMMANDS = {
    "add": cmd_add,         "a": cmd_add,
    "addm": cmd_addm,
    "append": cmd_append,   "app": cmd_append,
    "archive": cmd_archive,
    "command": cmd_command,
    "deduplicate": cmd_deduplicate,
    "del": cmd_del,         "rm": cmd_del,
    "depri": cmd_depri,     "dp": cmd_depri,
    "do": cmd_do,           "d": cmd_do,
    "done": cmd_do,
    "help": cmd_help,
    "list": cmd_list,       "ls": cmd_list,
    "listall": cmd_listall, "lsa": cmd_listall,
    "listfile": cmd_listfile, "lf": cmd_listfile,
    "listcon": cmd_listcon, "lsc": cmd_listcon,
    "listproj": cmd_listproj, "lsprj": cmd_listproj, "lsproj": cmd_listproj,
    "listpri": cmd_listpri, "lsp": cmd_listpri,
    "listaddons": cmd_listaddons,
    "move": cmd_move,       "mv": cmd_move,
    "prepend": cmd_prepend, "prep": cmd_prepend,
    "pri": cmd_pri,         "p": cmd_pri,
    "replace": cmd_replace,
    "report": cmd_report,
    "shorthelp": cmd_shorthelp,
    "undone": cmd_undone,   "u": cmd_undone,
    "completion": cmd_completion,
}


def main():
    argv = sys.argv[1:]
    argv = _parse_flags(argv)

    if not argv or argv[0] in ("help",):
        print(USAGE); sys.exit(0)

    cmd = argv[0]
    fn = COMMANDS.get(cmd)
    if not fn:
        print(f"TODO: Unknown command '{cmd}'. Run 'todo help'.", file=sys.stderr)
        sys.exit(1)
    fn(argv[1:])


if __name__ == "__main__":
    main()
