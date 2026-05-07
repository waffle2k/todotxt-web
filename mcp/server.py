#!/usr/bin/env python3
"""MCP server for the todo.txt web app.

Exposes todo task operations as Claude tools.

Environment variables:
  TODOTXT_WEB_URL   Base URL of the todo.txt web instance (default: http://localhost:5000)
  TODOTXT_USER      Login username
  TODOTXT_PASS      Login password
"""

import os

import requests
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("TODOTXT_WEB_URL", "http://localhost:5000").rstrip("/")

mcp = FastMCP("todotxt")
_session = requests.Session()
_authenticated = False


def _login():
    global _authenticated
    user = os.environ.get("TODOTXT_USER", "")
    passwd = os.environ.get("TODOTXT_PASS", "")
    if not user or not passwd:
        raise RuntimeError("Set TODOTXT_USER and TODOTXT_PASS environment variables.")
    resp = _session.post(
        f"{BASE_URL}/login",
        data={"username": user, "password": passwd, "remember": "on"},
        allow_redirects=True,
    )
    _authenticated = resp.ok and "/login" not in resp.url


def _get(path: str, **kwargs):
    global _authenticated
    if not _authenticated:
        _login()
    resp = _session.get(f"{BASE_URL}{path}", allow_redirects=True, **kwargs)
    if resp.url.endswith("/login"):
        _login()
        resp = _session.get(f"{BASE_URL}{path}", allow_redirects=True, **kwargs)
    return resp


def _post(path: str, data: dict):
    global _authenticated
    if not _authenticated:
        _login()
    resp = _session.post(f"{BASE_URL}{path}", data=data, allow_redirects=True)
    if resp.url.endswith("/login"):
        _login()
        resp = _session.post(f"{BASE_URL}{path}", data=data, allow_redirects=True)
    return resp


@mcp.tool()
def list_tasks(
    search: str = "",
    priority: str = "all",
    project: str = "all",
    context: str = "all",
    completed: str = "all",
) -> list[dict]:
    """List todo tasks.

    completed: 'all', 'completed', or 'incomplete'
    priority:  'all', 'A', 'B', 'C', or 'none'

    Returns a list of task dicts with: id, description, completed, priority,
    projects, contexts, creation_date, completion_date, raw_line.
    """
    resp = _get(
        "/api/search",
        params={
            "q": search,
            "priority": priority,
            "project": project,
            "context": context,
            "completed": completed,
        },
    )
    resp.raise_for_status()
    return resp.json()["tasks"]


@mcp.tool()
def add_task(
    description: str,
    priority: str = "",
    projects: str = "",
    contexts: str = "",
) -> str:
    """Add a new todo task.

    projects: comma-separated, e.g. 'homelab,work'
    contexts: comma-separated, e.g. 'home,weekend'
    priority: single uppercase letter A-Z, or empty for none
    """
    resp = _post(
        "/add",
        data={
            "description": description,
            "priority": priority,
            "projects": projects,
            "contexts": contexts,
        },
    )
    if resp.ok:
        return "Task added."
    return f"Failed (HTTP {resp.status_code})."


@mcp.tool()
def complete_task(task_id: int) -> str:
    """Mark a task as completed. Use list_tasks to find the task id."""
    resp = _get(f"/complete/{task_id}")
    if resp.ok:
        return f"Task {task_id} marked complete."
    return f"Failed (HTTP {resp.status_code})."


@mcp.tool()
def uncomplete_task(task_id: int) -> str:
    """Mark a completed task as incomplete. Use list_tasks to find the task id."""
    resp = _get(f"/complete/{task_id}")
    if resp.ok:
        return f"Task {task_id} marked incomplete."
    return f"Failed (HTTP {resp.status_code})."


@mcp.tool()
def edit_task(
    task_id: int,
    description: str,
    priority: str = "",
    projects: str = "",
    contexts: str = "",
) -> str:
    """Edit an existing task by id.

    projects: comma-separated, e.g. 'homelab,work'
    contexts: comma-separated, e.g. 'home,weekend'
    """
    resp = _post(
        f"/edit/{task_id}",
        data={
            "description": description,
            "priority": priority,
            "projects": projects,
            "contexts": contexts,
        },
    )
    if resp.ok:
        return f"Task {task_id} updated."
    return f"Failed (HTTP {resp.status_code})."


@mcp.tool()
def delete_task(task_id: int) -> str:
    """Permanently delete a task by id. Use list_tasks to find the task id."""
    resp = _get(f"/delete/{task_id}")
    if resp.ok:
        return f"Task {task_id} deleted."
    return f"Failed (HTTP {resp.status_code})."


if __name__ == "__main__":
    mcp.run()
