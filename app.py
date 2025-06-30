from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from todo_parser import TodoParser
from user_manager import UserManager
import os
import base64
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

@login_manager.user_loader
def load_user(username):
    return user_manager.get_user(username)

def get_user_todo_parser():
    """Get TodoParser instance for current user"""
    if current_user.is_authenticated:
        user_todo_file = user_manager.get_user_todo_file(current_user.username)
        return TodoParser(user_todo_file)
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
        
        # Authenticate user
        user = user_manager.authenticate_user(auth.username, auth.password)
        if not user:
            return Response(
                'Invalid credentials',
                401,
                {'WWW-Authenticate': 'Basic realm="Todo API"'}
            )
        
        # Store authenticated user in request context
        request.authenticated_user = user
        return f(*args, **kwargs)
    
    return decorated_function

def get_api_user_todo_parser():
    """Get TodoParser instance for API authenticated user"""
    if hasattr(request, 'authenticated_user'):
        user_todo_file = user_manager.get_user_todo_file(request.authenticated_user.username)
        return TodoParser(user_todo_file)
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
            
            # Redirect to next page or index
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
    # Get filter parameters
    search_term = request.args.get('search', '')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project', 'all')
    context_filter = request.args.get('context', 'all')
    completed_filter = request.args.get('completed', 'all')
    
    # Get user's todo parser
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('logout'))
    
    # Reload tasks to get latest data
    todo_parser.load_tasks()
    
    # Get filtered tasks
    filtered_tasks = todo_parser.get_filtered_tasks(
        search_term, priority_filter, project_filter, context_filter, completed_filter
    )
    
    # Get all projects and contexts for filter dropdowns
    all_projects = todo_parser.get_all_projects()
    all_contexts = todo_parser.get_all_contexts()
    
    # Calculate statistics
    total_tasks = len(todo_parser.tasks)
    completed_tasks = len([t for t in todo_parser.tasks if t.completed])
    incomplete_tasks = total_tasks - completed_tasks
    
    # Priority distribution
    priority_counts = {'A': 0, 'B': 0, 'C': 0, 'None': 0}
    for task in todo_parser.tasks:
        if not task.completed:  # Only count incomplete tasks
            if task.priority:
                priority_counts[task.priority] += 1
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
    todo_parser = get_user_todo_parser()
    if not todo_parser:
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
        
        # Parse projects and contexts
        projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        contexts = [c.strip() for c in contexts_str.split(',') if c.strip()]
        
        # Add the task
        try:
            todo_parser.add_task(
                description=description,
                priority=priority if priority else None,
                projects=projects if projects else None,
                contexts=contexts if contexts else None
            )
            flash('Task added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error adding task: {str(e)}', 'error')
            return redirect(url_for('add_task'))
    
    # GET request - show the form
    all_projects = todo_parser.get_all_projects()
    all_contexts = todo_parser.get_all_contexts()
    
    return render_template('add_task.html', 
                         all_projects=all_projects,
                         all_contexts=all_contexts)

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Edit an existing task"""
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    
    if task_id >= len(todo_parser.tasks):
        flash('Task not found!', 'error')
        return redirect(url_for('index'))
    
    task = todo_parser.tasks[task_id]
    
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        priority = request.form.get('priority', '')
        projects_str = request.form.get('projects', '')
        contexts_str = request.form.get('contexts', '')
        
        if not description:
            flash('Task description is required!', 'error')
            return redirect(url_for('edit_task', task_id=task_id))
        
        # Parse projects and contexts
        projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        contexts = [c.strip() for c in contexts_str.split(',') if c.strip()]
        
        # Update the task
        try:
            todo_parser.update_task(
                task_index=task_id,
                description=description,
                priority=priority if priority else None,
                projects=projects if projects else None,
                contexts=contexts if contexts else None
            )
            flash('Task updated successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error updating task: {str(e)}', 'error')
            return redirect(url_for('edit_task', task_id=task_id))
    
    # GET request - show the form with current values
    all_projects = todo_parser.get_all_projects()
    all_contexts = todo_parser.get_all_contexts()
    
    # Prepare current values for the form
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
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    
    if task_id >= len(todo_parser.tasks):
        flash('Task not found!', 'error')
        return redirect(url_for('index'))
    
    task = todo_parser.tasks[task_id]
    
    try:
        if task.completed:
            todo_parser.uncomplete_task(task_id)
            flash('Task marked as incomplete!', 'success')
        else:
            todo_parser.complete_task(task_id)
            flash('Task completed!', 'success')
    except Exception as e:
        flash(f'Error updating task: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    """Delete a task"""
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    
    if task_id >= len(todo_parser.tasks):
        flash('Task not found!', 'error')
        return redirect(url_for('index'))
    
    try:
        todo_parser.delete_task(task_id)
        flash('Task deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting task: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/api/search')
@login_required
def api_search():
    """AJAX endpoint for real-time search"""
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        return jsonify({'error': 'Error accessing todo list'}), 500
    
    search_term = request.args.get('q', '')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project', 'all')
    context_filter = request.args.get('context', 'all')
    completed_filter = request.args.get('completed', 'all')
    
    # Reload tasks to get latest data
    todo_parser.load_tasks()
    
    # Get filtered tasks
    filtered_tasks = todo_parser.get_filtered_tasks(
        search_term, priority_filter, project_filter, context_filter, completed_filter
    )
    
    # Convert tasks to JSON-serializable format
    tasks_data = []
    for task_id, task in filtered_tasks:
        tasks_data.append({
            'id': task_id,
            'description': task.description,
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
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    
    action = request.form.get('action')
    task_ids = request.form.getlist('task_ids')
    
    if not task_ids:
        flash('No tasks selected!', 'error')
        return redirect(url_for('index'))
    
    # Convert task IDs to integers
    try:
        task_ids = [int(tid) for tid in task_ids]
    except ValueError:
        flash('Invalid task IDs!', 'error')
        return redirect(url_for('index'))
    
    success_count = 0
    error_count = 0
    
    # Sort task IDs in reverse order for deletion to avoid index issues
    if action == 'delete':
        task_ids.sort(reverse=True)
    
    for task_id in task_ids:
        try:
            if action == 'complete':
                if task_id < len(todo_parser.tasks) and not todo_parser.tasks[task_id].completed:
                    todo_parser.complete_task(task_id)
                    success_count += 1
            elif action == 'uncomplete':
                if task_id < len(todo_parser.tasks) and todo_parser.tasks[task_id].completed:
                    todo_parser.uncomplete_task(task_id)
                    success_count += 1
            elif action == 'delete':
                if task_id < len(todo_parser.tasks):
                    todo_parser.delete_task(task_id)
                    success_count += 1
        except Exception:
            error_count += 1
    
    if success_count > 0:
        flash(f'Successfully processed {success_count} tasks!', 'success')
    if error_count > 0:
        flash(f'Failed to process {error_count} tasks!', 'error')
    
    return redirect(url_for('index'))

@app.route('/export')
@login_required
def export_todo():
    """Export the current user's todo.txt file"""
    todo_parser = get_user_todo_parser()
    if not todo_parser:
        flash('Error accessing your todo list.', 'error')
        return redirect(url_for('index'))
    
    try:
        user_todo_file = user_manager.get_user_todo_file(current_user.username)
        with open(user_todo_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        from flask import Response
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
            # Read the uploaded file content
            content = file.read().decode('utf-8')
            
            # Write to user's todo.txt file
            user_todo_file = user_manager.get_user_todo_file(current_user.username)
            with open(user_todo_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
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
    todo_parser = get_user_todo_parser()
    user_stats = {
        'total_tasks': 0,
        'completed_tasks': 0,
        'incomplete_tasks': 0,
        'total_projects': 0,
        'total_contexts': 0
    }
    
    if todo_parser:
        todo_parser.load_tasks()
        user_stats = {
            'total_tasks': len(todo_parser.tasks),
            'completed_tasks': len([t for t in todo_parser.tasks if t.completed]),
            'incomplete_tasks': len([t for t in todo_parser.tasks if not t.completed]),
            'total_projects': len(todo_parser.get_all_projects()),
            'total_contexts': len(todo_parser.get_all_contexts())
        }
    
    # Get the display path for the user's todo file
    user_todo_display_path = user_manager.get_user_todo_file_display_path(current_user.username)
    todo_directory = user_manager.get_todo_directory()
    
    return render_template('profile.html', 
                         user_stats=user_stats,
                         user_todo_display_path=user_todo_display_path,
                         todo_directory=todo_directory)

# REST API Endpoints with Basic Authentication

@app.route('/api/v1/todo', methods=['GET'])
@basic_auth_required
def api_get_todo():
    """REST API: Get todo.txt file content (Export functionality)"""
    try:
        user_todo_file = user_manager.get_user_todo_file(request.authenticated_user.username)
        with open(user_todo_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return Response(
            content,
            mimetype='text/plain',
            headers={
                'Content-Type': 'text/plain; charset=utf-8',
                'X-Username': request.authenticated_user.username
            }
        )
    except FileNotFoundError:
        return jsonify({
            'error': 'Todo file not found',
            'message': 'User todo file does not exist'
        }), 404
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@app.route('/api/v1/todo', methods=['POST'])
@basic_auth_required
def api_post_todo():
    """REST API: Update todo.txt file content (Import functionality)"""
    try:
        # Check content type
        if request.content_type and 'application/json' in request.content_type:
            # JSON payload with content field
            data = request.get_json()
            if not data or 'content' not in data:
                return jsonify({
                    'error': 'Bad request',
                    'message': 'JSON payload must contain "content" field'
                }), 400
            content = data['content']
        else:
            # Plain text payload
            content = request.get_data(as_text=True)
            if content is None:
                return jsonify({
                    'error': 'Bad request',
                    'message': 'Request body cannot be empty'
                }), 400
        
        # Validate content is a string
        if not isinstance(content, str):
            return jsonify({
                'error': 'Bad request',
                'message': 'Content must be a string'
            }), 400
        
        # Write to user's todo.txt file
        user_todo_file = user_manager.get_user_todo_file(request.authenticated_user.username)
        with open(user_todo_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Parse the file to validate and get statistics
        todo_parser = get_api_user_todo_parser()
        if todo_parser:
            todo_parser.load_tasks()
            task_count = len(todo_parser.tasks)
            completed_count = len([t for t in todo_parser.tasks if t.completed])
        else:
            task_count = 0
            completed_count = 0
        
        return jsonify({
            'success': True,
            'message': 'Todo file updated successfully',
            'username': request.authenticated_user.username,
            'statistics': {
                'total_tasks': task_count,
                'completed_tasks': completed_count,
                'incomplete_tasks': task_count - completed_count
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@app.route('/api/v1/todo/info', methods=['GET'])
@basic_auth_required
def api_get_todo_info():
    """REST API: Get todo file information and statistics"""
    try:
        todo_parser = get_api_user_todo_parser()
        if not todo_parser:
            return jsonify({
                'error': 'Internal server error',
                'message': 'Could not access todo file'
            }), 500
        
        todo_parser.load_tasks()
        
        # Calculate statistics
        total_tasks = len(todo_parser.tasks)
        completed_tasks = len([t for t in todo_parser.tasks if t.completed])
        incomplete_tasks = total_tasks - completed_tasks
        
        # Priority distribution
        priority_counts = {'A': 0, 'B': 0, 'C': 0, 'None': 0}
        for task in todo_parser.tasks:
            if not task.completed:  # Only count incomplete tasks
                if task.priority:
                    priority_counts[task.priority] += 1
                else:
                    priority_counts['None'] += 1
        
        # Get projects and contexts
        all_projects = todo_parser.get_all_projects()
        all_contexts = todo_parser.get_all_contexts()
        
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
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
