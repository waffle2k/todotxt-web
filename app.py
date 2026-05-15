from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, Response, stream_with_context, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from user_manager import UserManager
import todo_db
import os
import queue
import threading
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access your todo list.'
login_manager.login_message_category = 'info'

# Initialize user manager
user_manager = UserManager()

# Ensure each existing user has a DB (create schema + migrate from txt if needed)
for _username in user_manager.users:
    _db_path = user_manager.get_user_db_path(_username)
    if not todo_db.has_tasks(_db_path):
        _txt_file = user_manager.get_user_todo_file(_username)
        if os.path.exists(_txt_file):
            todo_db.migrate_from_file(_db_path, _txt_file)
        else:
            todo_db.create_sample_tasks(_db_path)
    else:
        todo_db.ensure_db(_db_path)

_backup_dir = os.path.join(user_manager.todo_dir, 'backups')

# SSE client queues — one per connected browser tab
_sse_clients = []
_sse_lock = threading.Lock()


def _notify_clients():
    """Push an update event to all connected SSE clients."""
    dead = []
    with _sse_lock:
        clients = list(_sse_clients)
    for q in clients:
        try:
            q.put_nowait("update")
        except queue.Full:
            dead.append(q)
    if dead:
        with _sse_lock:
            for q in dead:
                if q in _sse_clients:
                    _sse_clients.remove(q)


def _backup_and_notify(tdb: todo_db.TodoDb) -> None:
    """Write a dated backup snapshot then push SSE update to all clients."""
    try:
        todo_db.write_backup(tdb.db_path, _backup_dir)
    except Exception:
        pass  # backup failure must never break a write operation
    _notify_clients()


@login_manager.user_loader
def load_user(username):
    return user_manager.get_user(username)

def get_user_todo_db():
    """Get TodoDb instance for the current logged-in user."""
    if current_user.is_authenticated:
        db_path = user_manager.get_user_db_path(current_user.username)
        return todo_db.TodoDb(db_path)
    return None

def basic_auth_required(f):
    """Decorator for basic authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="Todo API"'}
            )

        user = user_manager.authenticate_user(auth.username, auth.password)
        if not user:
            return Response(
                'Invalid credentials',
                401,
                {'WWW-Authenticate': 'Basic realm="Todo API"'}
            )

        request.authenticated_user = user
        return f(*args, **kwargs)

    return decorated_function

def get_api_user_todo_db():
    """Get TodoDb instance for the API-authenticated user."""
    if hasattr(request, 'authenticated_user'):
        db_path = user_manager.get_user_db_path(request.authenticated_user.username)
        return todo_db.TodoDb(db_path)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')

        user = user_manager.authenticate_user(username, password)
        if user:
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.username}!', 'success')

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        user, message = user_manager.create_user(username, email, password)
        if user:
            db_path = user_manager.get_user_db_path(username)
            todo_db.create_sample_tasks(db_path)
            flash(message, 'success')
            flash('You can now log in with your credentials.', 'info')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    username = current_user.username
    logout_user()
    flash(f'Goodbye, {username}! You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main dashboard showing all tasks with filtering options"""
    search_term = request.args.get('search', '')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project', 'all')
    context_filter = request.args.get('context', 'all')
    completed_filter = request.args.get('completed', 'all')

    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('logout'))

    filtered_tasks = tdb.get_filtered_tasks(
        search_term, priority_filter, project_filter, context_filter, completed_filter
    )
    all_projects = tdb.get_all_projects()
    all_contexts = tdb.get_all_contexts()

    all_tasks = tdb.tasks
    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t.completed)
    incomplete_tasks = total_tasks - completed_tasks

    priority_counts = {'A': 0, 'B': 0, 'C': 0, 'None': 0}
    for task in all_tasks:
        if not task.completed:
            if task.priority:
                priority_counts[task.priority] = priority_counts.get(task.priority, 0) + 1
            else:
                priority_counts['None'] += 1

    return render_template('index.html',
                         tasks=filtered_tasks,
                         all_projects=all_projects,
                         all_contexts=all_contexts,
                         current_filters={
                             'search': search_term,
                             'priority': priority_filter,
                             'project': project_filter,
                             'context': context_filter,
                             'completed': completed_filter
                         },
                         stats={
                             'total': total_tasks,
                             'completed': completed_tasks,
                             'incomplete': incomplete_tasks,
                             'priorities': priority_counts
                         })

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_task():
    """Add a new task"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        priority = request.form.get('priority', '')
        projects_str = request.form.get('projects', '')
        contexts_str = request.form.get('contexts', '')

        if not description:
            flash('Task description is required!', 'error')
            return redirect(url_for('add_task'))

        projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        contexts = [c.strip() for c in contexts_str.split(',') if c.strip()]

        try:
            tdb.add_task(
                description=description,
                priority=priority if priority else None,
                projects=projects if projects else None,
                contexts=contexts if contexts else None
            )
            _backup_and_notify(tdb)
            flash('Task added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error adding task: {str(e)}', 'error')
            return redirect(url_for('add_task'))

    all_projects = tdb.get_all_projects()
    all_contexts = tdb.get_all_contexts()

    return render_template('add_task.html',
                         all_projects=all_projects,
                         all_contexts=all_contexts)

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Edit an existing task"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    task = tdb.get_task(task_id)
    if not task:
        flash('Task not found!', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        priority = request.form.get('priority', '')
        projects_str = request.form.get('projects', '')
        contexts_str = request.form.get('contexts', '')

        if not description:
            flash('Task description is required!', 'error')
            return redirect(url_for('edit_task', task_id=task_id))

        projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        contexts = [c.strip() for c in contexts_str.split(',') if c.strip()]

        try:
            tdb.update_task(
                task_id=task_id,
                description=description,
                priority=priority if priority else None,
                projects=projects if projects else None,
                contexts=contexts if contexts else None
            )
            _backup_and_notify(tdb)
            flash('Task updated successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error updating task: {str(e)}', 'error')
            return redirect(url_for('edit_task', task_id=task_id))

    all_projects = tdb.get_all_projects()
    all_contexts = tdb.get_all_contexts()
    current_projects = ', '.join(task.projects)
    current_contexts = ', '.join(task.contexts)

    return render_template('edit_task.html',
                         task=task,
                         task_id=task_id,
                         current_projects=current_projects,
                         current_contexts=current_contexts,
                         all_projects=all_projects,
                         all_contexts=all_contexts)

@app.route('/complete/<int:task_id>')
@login_required
def complete_task(task_id):
    """Toggle task completion status"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    task = tdb.get_task(task_id)
    if not task:
        flash('Task not found!', 'error')
        return redirect(url_for('index'))

    try:
        if task.completed:
            tdb.uncomplete_task(task_id)
            flash('Task marked as incomplete!', 'success')
        else:
            tdb.complete_task(task_id)
            flash('Task completed!', 'success')
    except Exception as e:
        flash(f'Error updating task: {str(e)}', 'error')
    else:
        _backup_and_notify(tdb)

    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    """Delete a task"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    try:
        if not tdb.delete_task(task_id):
            flash('Task not found!', 'error')
        else:
            _backup_and_notify(tdb)
            flash('Task deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting task: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/api/search')
@login_required
def api_search():
    """AJAX endpoint for real-time search"""
    tdb = get_user_todo_db()
    if not tdb:
        return jsonify({'error': 'Error accessing todo list'}), 500

    search_term = request.args.get('q', '')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project', 'all')
    context_filter = request.args.get('context', 'all')
    completed_filter = request.args.get('completed', 'all')

    filtered_tasks = tdb.get_filtered_tasks(
        search_term, priority_filter, project_filter, context_filter, completed_filter
    )

    tasks_data = []
    for task_id, task in filtered_tasks:
        tasks_data.append({
            'id': task_id,
            'description': task.get_clean_description(),
            'completed': task.completed,
            'priority': task.priority,
            'projects': task.projects,
            'contexts': task.contexts,
            'creation_date': task.creation_date,
            'completion_date': task.completion_date,
            'raw_line': task.raw_line
        })

    return jsonify({
        'tasks': tasks_data,
        'count': len(tasks_data)
    })

@app.route('/bulk_action', methods=['POST'])
@login_required
def bulk_action():
    """Handle bulk actions on multiple tasks"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    action = request.form.get('action')
    task_ids = request.form.getlist('task_ids')

    if not task_ids:
        flash('No tasks selected!', 'error')
        return redirect(url_for('index'))

    try:
        task_ids = [int(tid) for tid in task_ids]
    except ValueError:
        flash('Invalid task IDs!', 'error')
        return redirect(url_for('index'))

    success_count = 0
    error_count = 0

    for task_id in task_ids:
        try:
            if action == 'complete':
                if tdb.complete_task(task_id):
                    success_count += 1
            elif action == 'uncomplete':
                if tdb.uncomplete_task(task_id):
                    success_count += 1
            elif action == 'delete':
                if tdb.delete_task(task_id):
                    success_count += 1
        except Exception:
            error_count += 1

    if success_count > 0:
        _backup_and_notify(tdb)
        flash(f'Successfully processed {success_count} tasks!', 'success')
    if error_count > 0:
        flash(f'Failed to process {error_count} tasks!', 'error')

    return redirect(url_for('index'))

@app.route('/journal')
@login_required
def view_journal():
    """Change journal — last 200 mutations for the current user."""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    entries = tdb.get_journal()
    return render_template('journal.html', entries=entries)


@app.route('/restore/<int:journal_id>', methods=['POST'])
@login_required
def restore_journal(journal_id):
    """Restore a task to its state before the given journal entry."""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('view_journal'))
    if tdb.restore_from_journal(journal_id):
        _backup_and_notify(tdb)
        flash('Task restored successfully.', 'success')
    else:
        flash('Could not restore — entry not found or operation has no before-state.', 'error')
    return redirect(url_for('view_journal'))


@app.route('/export')
@login_required
def export_todo():
    """Export the current user's tasks as todo.txt"""
    tdb = get_user_todo_db()
    if not tdb:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))

    try:
        content = tdb.to_todo_txt()
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename=todo_{current_user.username}.txt'}
        )
    except Exception as e:
        flash(f'Error exporting file: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/import', methods=['POST'])
@login_required
def import_todo():
    """Import a todo.txt file for the current user"""
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('index'))

    if file and file.filename.endswith('.txt'):
        try:
            content = file.read().decode('utf-8')
            tdb = get_user_todo_db()
            if not tdb:
                flash('Error accessing your todo list.', 'error')
                return redirect(url_for('index'))
            tdb.replace_from_txt(content)
            _backup_and_notify(tdb)
            flash('File imported successfully!', 'success')
        except Exception as e:
            flash(f'Error importing file: {str(e)}', 'error')
    else:
        flash('Please upload a .txt file!', 'error')

    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    tdb = get_user_todo_db()
    user_stats = {
        'total_tasks': 0,
        'completed_tasks': 0,
        'incomplete_tasks': 0,
        'total_projects': 0,
        'total_contexts': 0
    }

    if tdb:
        all_tasks = tdb.tasks
        user_stats = {
            'total_tasks': len(all_tasks),
            'completed_tasks': sum(1 for t in all_tasks if t.completed),
            'incomplete_tasks': sum(1 for t in all_tasks if not t.completed),
            'total_projects': len(tdb.get_all_projects()),
            'total_contexts': len(tdb.get_all_contexts())
        }

    heatmap = tdb.get_completion_heatmap() if tdb else []

    user_todo_display_path = user_manager.get_user_db_path(current_user.username)
    todo_directory = user_manager.get_todo_directory()

    return render_template('profile.html',
                         user_stats=user_stats,
                         heatmap=heatmap,
                         user_todo_display_path=user_todo_display_path,
                         todo_directory=todo_directory)

# REST API Endpoints with Basic Authentication

@app.route('/api/v1/todo', methods=['GET'])
@basic_auth_required
def api_get_todo():
    """REST API: Export tasks as todo.txt content"""
    try:
        tdb = get_api_user_todo_db()
        if not tdb:
            return jsonify({'error': 'Internal server error', 'message': 'Could not access todo data'}), 500
        content = tdb.to_todo_txt()
        return Response(
            content,
            mimetype='text/plain',
            headers={
                'Content-Type': 'text/plain; charset=utf-8',
                'X-Username': request.authenticated_user.username
            }
        )
    except Exception as e:
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

@app.route('/api/v1/todo', methods=['POST'])
@basic_auth_required
def api_post_todo():
    """REST API: Replace tasks from todo.txt content"""
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
            if not data or 'content' not in data:
                return jsonify({'error': 'Bad request', 'message': 'JSON payload must contain "content" field'}), 400
            content = data['content']
        else:
            content = request.get_data(as_text=True)
            if content is None:
                return jsonify({'error': 'Bad request', 'message': 'Request body cannot be empty'}), 400

        if not isinstance(content, str):
            return jsonify({'error': 'Bad request', 'message': 'Content must be a string'}), 400

        tdb = get_api_user_todo_db()
        if not tdb:
            return jsonify({'error': 'Internal server error', 'message': 'Could not access todo data'}), 500

        tdb.replace_from_txt(content)
        all_tasks = tdb.tasks
        task_count = len(all_tasks)
        completed_count = sum(1 for t in all_tasks if t.completed)

        _backup_and_notify(tdb)
        return jsonify({
            'success': True,
            'message': 'Todo data updated successfully',
            'username': request.authenticated_user.username,
            'statistics': {
                'total_tasks': task_count,
                'completed_tasks': completed_count,
                'incomplete_tasks': task_count - completed_count
            }
        }), 200

    except Exception as e:
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

@app.route('/api/v1/todo/info', methods=['GET'])
@basic_auth_required
def api_get_todo_info():
    """REST API: Get task statistics"""
    try:
        tdb = get_api_user_todo_db()
        if not tdb:
            return jsonify({'error': 'Internal server error', 'message': 'Could not access todo data'}), 500

        all_tasks = tdb.tasks
        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t.completed)
        incomplete_tasks = total_tasks - completed_tasks

        priority_counts = {'A': 0, 'B': 0, 'C': 0, 'None': 0}
        for task in all_tasks:
            if not task.completed:
                if task.priority:
                    priority_counts[task.priority] = priority_counts.get(task.priority, 0) + 1
                else:
                    priority_counts['None'] += 1

        all_projects = tdb.get_all_projects()
        all_contexts = tdb.get_all_contexts()

        return jsonify({
            'username': request.authenticated_user.username,
            'statistics': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'incomplete_tasks': incomplete_tasks,
                'priority_distribution': priority_counts,
                'total_projects': len(all_projects),
                'total_contexts': len(all_contexts)
            },
            'projects': sorted(all_projects),
            'contexts': sorted(all_contexts)
        }), 200

    except Exception as e:
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

import re as _re
_DOWNLOAD_RE = _re.compile(r'^(todo|todotui-[a-z]+-[a-z0-9_]+)(\.sha256)?$')

@app.route('/download/<filename>')
def download_file(filename):
    if not _DOWNLOAD_RE.match(filename):
        abort(404)
    downloads_dir = os.path.join(user_manager.todo_dir, 'downloads')
    response = send_from_directory(downloads_dir, filename, as_attachment=True)
    if filename.endswith('.sha256'):
        response.headers['Cache-Control'] = 'no-store'
    return response


_INSTALL_SH = """\
#!/bin/sh
set -e
BASE_URL="{base_url}"
BIN_DIR="${{BIN_DIR:-$HOME/bin}}"

# Normalise OS name to match binary naming
case "$(uname -s)" in
  Linux)  OS=linux  ;;
  Darwin) OS=macos  ;;
  *)      echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64)   ARCH=aarch64 ;;
  *)       ARCH=$(uname -m) ;;
esac

mkdir -p "$BIN_DIR"

# todotui — compiled binary
TODOTUI="${{TODOTUI_DEST:-$BIN_DIR/todotui}}"
echo "Downloading todotui-$OS-$ARCH ..."
curl -fsSL "$BASE_URL/download/todotui-$OS-$ARCH" -o "$TODOTUI"
chmod +x "$TODOTUI"
echo "Installed: $TODOTUI"

# todo — Python CLI (requires python3 + requests)
TODO="${{TODO_DEST:-$BIN_DIR/todo}}"
echo "Downloading todo ..."
curl -fsSL "$BASE_URL/download/todo" -o "$TODO"
chmod +x "$TODO"
echo "Installed: $TODO"

echo ""

# Neovim plugin — installed automatically when nvim + lazy.nvim are detected
if command -v nvim >/dev/null 2>&1; then
  NVIM_LUA="${{NVIM_LUA:-$HOME/.config/nvim/lua}}"
  NVIM_PLUGINS="$NVIM_LUA/plugins"
  if [ -d "$NVIM_PLUGINS" ]; then
    echo "Neovim detected — installing todo.lua plugin ..."
    curl -fsSL "$BASE_URL/nvim/todo.lua"         -o "$NVIM_LUA/todo.lua"
    curl -fsSL "$BASE_URL/nvim/plugins/todo.lua" -o "$NVIM_PLUGINS/todo.lua"
    echo "Installed: $NVIM_LUA/todo.lua"
    echo "Installed: $NVIM_PLUGINS/todo.lua"
    echo "Run :Lazy sync in neovim to activate."
  else
    echo "Neovim found but no lazy.nvim plugins dir — skipping plugin install."
    echo "  (expected: $NVIM_PLUGINS)"
  fi
fi

echo ""
echo "Configure via ~/.config/todotui/config:"
echo "  TODO_URL=https://your-todo-server"
echo "  TODO_USER=youruser"
echo "  TODO_PASS=yourpass"
"""

@app.route('/install.sh')
def install_sh():
    proto = request.headers.get('X-Forwarded-Proto', request.scheme)
    base_url = f"{proto}://{request.host}"
    return app.response_class(
        _INSTALL_SH.format(base_url=base_url),
        mimetype='text/plain',
    )


_NVIM_DIR = os.path.join(os.path.dirname(__file__), 'nvim')
_NVIM_RE  = _re.compile(r'^(plugins/)?todo\.lua$')

@app.route('/nvim/<path:filename>')
def nvim_file(filename):
    if not _NVIM_RE.match(filename):
        abort(404)
    return send_from_directory(_NVIM_DIR, filename, mimetype='text/plain')


@app.route('/events')
@login_required
def events():
    """SSE endpoint — browser connects here to receive real-time task change notifications."""
    def stream():
        q = queue.Queue(maxsize=10)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            # Padding flushes Cloudflare's ~4KB response buffer so events
            # arrive in the browser immediately rather than being held.
            yield ": " + " " * 4096 + "\n\n"
            yield "data: connected\n\n"
            while True:
                try:
                    event = q.get(timeout=25)
                    # Pad to flush Cloudflare's per-chunk buffer
                    yield f"data: {event}\n\n: {' ' * 4096}\n\n"
                except queue.Empty:
                    # Heartbeat keeps connection alive through proxies
                    yield ": heartbeat\n\n"
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    return Response(
        stream_with_context(stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
