import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from todo_parser import TodoTask

_initialized: set = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    completed       INTEGER NOT NULL DEFAULT 0,
    priority        TEXT,
    creation_date   TEXT,
    completion_date TEXT,
    description     TEXT NOT NULL DEFAULT '',
    raw_line        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_projects (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    project TEXT    NOT NULL,
    PRIMARY KEY (task_id, project)
);
CREATE INDEX IF NOT EXISTS idx_tp_project ON task_projects(project);

CREATE TABLE IF NOT EXISTS task_contexts (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    context TEXT    NOT NULL,
    PRIMARY KEY (task_id, context)
);
CREATE INDEX IF NOT EXISTS idx_tc_context ON task_contexts(context);

CREATE TABLE IF NOT EXISTS task_journal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER,
    operation   TEXT NOT NULL,
    before_raw  TEXT,
    after_raw   TEXT,
    actor       TEXT,
    ts          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_journal_ts      ON task_journal(ts DESC);
CREATE INDEX IF NOT EXISTS idx_journal_task_id ON task_journal(task_id);
"""


@contextmanager
def _db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-16000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_db(db_path: str) -> None:
    if db_path in _initialized:
        return
    with _db(db_path) as conn:
        conn.executescript(_SCHEMA)
    _initialized.add(db_path)


def has_tasks(db_path: str) -> bool:
    ensure_db(db_path)
    with _db(db_path) as conn:
        row = conn.execute("SELECT 1 FROM tasks LIMIT 1").fetchone()
    return row is not None


def migrate_from_file(db_path: str, filepath: str) -> int:
    """One-time import from a todo.txt file. Returns number of tasks imported."""
    ensure_db(db_path)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return 0
    count = 0
    with _db(db_path) as conn:
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            t = TodoTask(line)
            task_id = conn.execute(
                """INSERT INTO tasks (completed, priority, creation_date, completion_date,
                   description, raw_line) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    1 if t.completed else 0,
                    t.priority,
                    t.creation_date,
                    t.completion_date,
                    t.get_clean_description(),
                    t.raw_line,
                ),
            ).lastrowid
            _insert_tags(conn, task_id, t.projects, t.contexts)
            count += 1
    return count


def create_sample_tasks(db_path: str) -> None:
    ensure_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    samples = [
        ("A", today, "Welcome to your personal todo.txt manager!", ["welcome"], ["computer"]),
        (None, today, "Add your first task", ["gettingstarted"], ["anywhere"]),
        ("B", today, "Explore the filtering and search features", ["tutorial"], ["computer"]),
    ]
    with _db(db_path) as conn:
        for priority, creation_date, description, projects, contexts in samples:
            raw = _build_raw_line(priority, creation_date, None, False, description, projects, contexts)
            task_id = conn.execute(
                """INSERT INTO tasks (completed, priority, creation_date, description, raw_line)
                   VALUES (?, ?, ?, ?, ?)""",
                (0, priority, creation_date, description, raw),
            ).lastrowid
            _insert_tags(conn, task_id, projects, contexts)


def _clean_desc(text: str) -> str:
    text = re.sub(r"\s*\+\w+", "", text)
    text = re.sub(r"\s*@\w+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_raw_line(
    priority: Optional[str],
    creation_date: Optional[str],
    completion_date: Optional[str],
    completed: bool,
    description: str,
    projects: List[str],
    contexts: List[str],
) -> str:
    parts = []
    if completed:
        parts.append("x")
        if completion_date:
            parts.append(completion_date)
    if priority and not completed:
        parts.append(f"({priority})")
    if creation_date:
        parts.append(creation_date)
    desc = description
    seen_p: set = set()
    seen_c: set = set()
    for p in projects:
        p = p.lower().strip()
        if p and p not in seen_p:
            desc += f" +{p}"
            seen_p.add(p)
    for c in contexts:
        c = c.lower().strip()
        if c and c not in seen_c:
            desc += f" @{c}"
            seen_c.add(c)
    parts.append(desc)
    return " ".join(parts)


def write_backup(db_path: str, backup_dir: str) -> str:
    """Write a dated todo.txt snapshot to backup_dir. Returns the backup file path."""
    os.makedirs(backup_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(db_path))[0]  # "todo_pmb"
    today = datetime.now().strftime("%Y-%m-%d")
    backup_file = os.path.join(backup_dir, f"{stem}_{today}.txt")
    with _db(db_path) as conn:
        rows = conn.execute("SELECT raw_line FROM tasks ORDER BY id").fetchall()
    content = "\n".join(r["raw_line"] for r in rows)
    if content:
        content += "\n"
    with open(backup_file, "w", encoding="utf-8") as f:
        f.write(content)
    return backup_file


def _log_journal(conn, task_id, operation: str, before_raw, after_raw, actor) -> None:
    conn.execute(
        """INSERT INTO task_journal (task_id, operation, before_raw, after_raw, actor)
           VALUES (?, ?, ?, ?, ?)""",
        (task_id, operation, before_raw, after_raw, actor),
    )


def _insert_tags(conn, task_id: int, projects: List[str], contexts: List[str]) -> None:
    seen_p: set = set()
    seen_c: set = set()
    for p in projects:
        p = p.lower().strip()
        if p and p not in seen_p:
            conn.execute(
                "INSERT OR IGNORE INTO task_projects (task_id, project) VALUES (?, ?)",
                (task_id, p),
            )
            seen_p.add(p)
    for c in contexts:
        c = c.lower().strip()
        if c and c not in seen_c:
            conn.execute(
                "INSERT OR IGNORE INTO task_contexts (task_id, context) VALUES (?, ?)",
                (task_id, c),
            )
            seen_c.add(c)


def _sync_tags(conn, task_id: int, projects: List[str], contexts: List[str]) -> None:
    conn.execute("DELETE FROM task_projects WHERE task_id=?", (task_id,))
    conn.execute("DELETE FROM task_contexts WHERE task_id=?", (task_id,))
    _insert_tags(conn, task_id, projects, contexts)


class TodoDb:
    def __init__(self, db_path: str):
        self.db_path = db_path
        stem = os.path.splitext(os.path.basename(db_path))[0]
        self.actor = stem[5:] if stem.startswith('todo_') else stem
        ensure_db(db_path)

    def load_tasks(self) -> None:
        """No-op — kept for interface compatibility with TodoParser."""
        pass

    @property
    def tasks(self) -> List[TodoTask]:
        with _db(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [TodoTask(r["raw_line"], line_number=r["id"]) for r in rows]

    def get_task(self, task_id: int) -> Optional[TodoTask]:
        with _db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return TodoTask(row["raw_line"], line_number=row["id"]) if row else None

    def add_task(
        self,
        description: str,
        priority: str = None,
        projects: List[str] = None,
        contexts: List[str] = None,
    ) -> TodoTask:
        creation_date = datetime.now().strftime("%Y-%m-%d")
        inline_p = re.findall(r'(?<!\S)\+(\w+)', description)
        inline_c = re.findall(r'(?<!\S)@(\w+)', description)
        projects = list({p.lower() for p in (projects or []) + inline_p})
        contexts = list({c.lower() for c in (contexts or []) + inline_c})
        clean = _clean_desc(description)
        raw = _build_raw_line(priority, creation_date, None, False, clean, projects, contexts)
        with _db(self.db_path) as conn:
            task_id = conn.execute(
                """INSERT INTO tasks (completed, priority, creation_date, description, raw_line)
                   VALUES (?, ?, ?, ?, ?)""",
                (0, priority or None, creation_date, clean, raw),
            ).lastrowid
            _sync_tags(conn, task_id, projects, contexts)
            _log_journal(conn, task_id, 'add', None, raw, self.actor)
        return self.get_task(task_id)

    def update_task(
        self,
        task_id: int,
        description: str,
        priority: str = None,
        projects: List[str] = None,
        contexts: List[str] = None,
    ) -> bool:
        inline_p = re.findall(r'(?<!\S)\+(\w+)', description)
        inline_c = re.findall(r'(?<!\S)@(\w+)', description)
        projects = list({p.lower() for p in (projects or []) + inline_p})
        contexts = list({c.lower() for c in (contexts or []) + inline_c})
        clean = _clean_desc(description)
        with _db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return False
            before_raw = row["raw_line"]
            raw = _build_raw_line(
                priority, row["creation_date"], row["completion_date"],
                bool(row["completed"]), clean, projects, contexts,
            )
            conn.execute(
                """UPDATE tasks SET description=?, priority=?, raw_line=?,
                   updated_at=datetime('now') WHERE id=?""",
                (clean, priority or None, raw, task_id),
            )
            _sync_tags(conn, task_id, projects, contexts)
            _log_journal(conn, task_id, 'update', before_raw, raw, self.actor)
        return True

    def complete_task(self, task_id: int) -> bool:
        completion_date = datetime.now().strftime("%Y-%m-%d")
        with _db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=? AND completed=0", (task_id,)
            ).fetchone()
            if not row:
                return False
            new_raw = f"x {completion_date} {row['raw_line']}"
            conn.execute(
                """UPDATE tasks SET completed=1, completion_date=?, priority=NULL, raw_line=?,
                   updated_at=datetime('now') WHERE id=?""",
                (completion_date, new_raw, task_id),
            )
            _log_journal(conn, task_id, 'complete', row['raw_line'], new_raw, self.actor)
        return True

    def uncomplete_task(self, task_id: int) -> bool:
        with _db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=? AND completed=1", (task_id,)
            ).fetchone()
            if not row:
                return False
            before_raw = row["raw_line"]
            raw = before_raw
            if raw.startswith("x "):
                raw = raw[2:]
                m = re.match(r"^\d{4}-\d{2}-\d{2}\s+", raw)
                if m:
                    raw = raw[len(m.group(0)):]
            pri_match = re.match(r"^\(([A-Z])\)\s+", raw)
            priority = pri_match.group(1) if pri_match else None
            conn.execute(
                """UPDATE tasks SET completed=0, completion_date=NULL, priority=?, raw_line=?,
                   updated_at=datetime('now') WHERE id=?""",
                (priority, raw, task_id),
            )
            _log_journal(conn, task_id, 'uncomplete', before_raw, raw, self.actor)
        return True

    def delete_task(self, task_id: int) -> bool:
        with _db(self.db_path) as conn:
            row = conn.execute("SELECT raw_line FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            _log_journal(conn, task_id, 'delete', row['raw_line'], None, self.actor)
        return True

    def get_filtered_tasks(
        self,
        search_term: str = "",
        priority_filter: str = "",
        project_filter: str = "",
        context_filter: str = "",
        completed_filter: str = "",
    ) -> List[Tuple[int, TodoTask]]:
        conditions: List[str] = []
        params: List = []
        joins: List[str] = []

        if project_filter and project_filter != "all":
            joins.append("JOIN task_projects tp ON tp.task_id = t.id")
            conditions.append("tp.project = ?")
            params.append(project_filter.lower())

        if context_filter and context_filter != "all":
            joins.append("JOIN task_contexts tc ON tc.task_id = t.id")
            conditions.append("tc.context = ?")
            params.append(context_filter.lower())

        if completed_filter == "completed":
            conditions.append("t.completed = 1")
        elif completed_filter == "incomplete":
            conditions.append("t.completed = 0")

        if priority_filter and priority_filter != "all":
            if priority_filter == "none":
                conditions.append("t.priority IS NULL")
            else:
                conditions.append("t.priority = ?")
                params.append(priority_filter.upper())

        if search_term:
            conditions.append("t.raw_line LIKE ?")
            params.append(f"%{search_term}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        join_str = " ".join(joins)
        query = f"""
            SELECT DISTINCT t.* FROM tasks t {join_str} {where}
            ORDER BY
                t.completed ASC,
                CASE t.priority WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                    ELSE 3 END ASC,
                t.id ASC
        """
        with _db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [(r["id"], TodoTask(r["raw_line"], line_number=r["id"])) for r in rows]

    def get_all_projects(self) -> List[str]:
        with _db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM task_projects ORDER BY project"
            ).fetchall()
        return [r["project"] for r in rows]

    def get_all_contexts(self) -> List[str]:
        with _db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT context FROM task_contexts ORDER BY context"
            ).fetchall()
        return [r["context"] for r in rows]

    def get_journal(self, limit: int = 200) -> list:
        with _db(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, task_id, operation, before_raw, after_raw, actor, ts
                   FROM task_journal ORDER BY ts DESC, id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def restore_from_journal(self, journal_id: int) -> bool:
        """Restore a task to its state before the given journal entry."""
        with _db(self.db_path) as conn:
            entry = conn.execute(
                "SELECT * FROM task_journal WHERE id=?", (journal_id,)
            ).fetchone()
            if not entry or not entry['before_raw'] or entry['operation'] in ('add', 'replace_all'):
                return False
            task_id = entry['task_id']
            t = TodoTask(entry['before_raw'])
            existing = conn.execute(
                "SELECT id FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE tasks SET completed=?, priority=?, creation_date=?,
                       completion_date=?, description=?, raw_line=?,
                       updated_at=datetime('now') WHERE id=?""",
                    (1 if t.completed else 0, t.priority, t.creation_date,
                     t.completion_date, t.get_clean_description(), t.raw_line, task_id),
                )
                _sync_tags(conn, task_id, t.projects, t.contexts)
            else:
                conn.execute(
                    """INSERT INTO tasks (id, completed, priority, creation_date,
                       completion_date, description, raw_line)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, 1 if t.completed else 0, t.priority, t.creation_date,
                     t.completion_date, t.get_clean_description(), t.raw_line),
                )
                _insert_tags(conn, task_id, t.projects, t.contexts)
            _log_journal(conn, task_id, 'restore', entry['after_raw'], entry['before_raw'], self.actor)
        return True

    def get_completion_heatmap(self) -> list:
        """Return 52 weeks of daily completion counts for a GitHub-style heatmap.

        Each entry: {'days': [...], 'month_label': str|None}
        Each day:   {'date': 'YYYY-MM-DD', 'count': int, 'level': 0-4, 'future': bool}
        """
        today = date.today()
        # Align to the Sunday of the current week, then go back 51 more weeks
        current_week_sun = today - timedelta(days=(today.weekday() + 1) % 7)
        start = current_week_sun - timedelta(weeks=51)

        with _db(self.db_path) as conn:
            rows = conn.execute(
                """SELECT date(ts) AS day, COUNT(*) AS cnt
                   FROM task_journal
                   WHERE operation = 'complete' AND date(ts) >= ?
                   GROUP BY day""",
                (start.isoformat(),),
            ).fetchall()
        counts = {r['day']: r['cnt'] for r in rows}

        weeks = []
        prev_month = None
        for w in range(52):
            week_start = start + timedelta(days=w * 7)
            month_label = week_start.strftime('%b') if week_start.month != prev_month else None
            prev_month = week_start.month
            days = []
            for d in range(7):
                day = week_start + timedelta(days=d)
                day_str = day.isoformat()
                cnt = counts.get(day_str, 0)
                level = 0 if cnt == 0 else 1 if cnt == 1 else 2 if cnt <= 3 else 3 if cnt <= 6 else 4
                days.append({'date': day_str, 'count': cnt, 'level': level, 'future': day > today})
            weeks.append({'days': days, 'month_label': month_label})
        return weeks

    def to_todo_txt(self) -> str:
        """Export all tasks as todo.txt content using stored raw_line."""
        with _db(self.db_path) as conn:
            rows = conn.execute("SELECT raw_line FROM tasks ORDER BY id").fetchall()
        lines = [r["raw_line"] for r in rows]
        return "\n".join(lines) + ("\n" if lines else "")

    def replace_from_txt(self, content: str) -> int:
        """Replace all tasks from todo.txt content. Returns count imported."""
        count = 0
        with _db(self.db_path) as conn:
            old_rows = conn.execute("SELECT raw_line FROM tasks ORDER BY id").fetchall()
            before_raw = "\n".join(r["raw_line"] for r in old_rows) or None
            conn.execute("DELETE FROM tasks")
            after_lines = []
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                t = TodoTask(line)
                task_id = conn.execute(
                    """INSERT INTO tasks (completed, priority, creation_date, completion_date,
                       description, raw_line) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        1 if t.completed else 0,
                        t.priority,
                        t.creation_date,
                        t.completion_date,
                        t.get_clean_description(),
                        t.raw_line,
                    ),
                ).lastrowid
                _insert_tags(conn, task_id, t.projects, t.contexts)
                after_lines.append(t.raw_line)
                count += 1
            _log_journal(conn, None, 'replace_all', before_raw, "\n".join(after_lines) or None, self.actor)
        return count
