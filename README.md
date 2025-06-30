# Todo.txt Web Manager

A Flask web application for managing todo.txt files via a web interface with user authentication and terminal styling.

## Features

- **User Authentication**: Secure registration, login, and session management
- **Individual Todo Files**: Each user gets their own isolated todo.txt file
- **Terminal Styling**: Authentic terminal interface with dark theme and green accents
- **Full Todo.txt Support**: Priorities, projects (+project), contexts (@context), dates
- **Advanced Filtering**: Search, filter by priority/project/context/completion status
- **Bulk Operations**: Select multiple tasks for batch actions
- **Import/Export**: Download or upload todo.txt files
- **Real-time Statistics**: Task counts, project/context statistics
- **Responsive Design**: Works on desktop and mobile devices

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your browser to `http://localhost:5000`

## Configuration

### Todo Files Directory

By default, user todo files are stored in the current directory. You can configure a different location using the `TODO_FILES_DIR` environment variable:

```bash
# Store todo files in a specific directory
export TODO_FILES_DIR="/path/to/todo/files"
python app.py
```

```bash
# Example: Store in a dedicated data directory
export TODO_FILES_DIR="./data/todos"
python app.py
```

```bash
# Example: Store in user's home directory
export TODO_FILES_DIR="$HOME/todos"
python app.py
```

The application will automatically create the directory if it doesn't exist.

### File Structure

When configured, user todo files will be stored as:
- `{TODO_FILES_DIR}/todo_username.txt`

For example, with `TODO_FILES_DIR="/var/lib/todos"`:
- User "alice" → `/var/lib/todos/todo_alice.txt`
- User "bob" → `/var/lib/todos/todo_bob.txt`

## Usage

1. **Register**: Create a new account with username, email, and password
2. **Login**: Access your personal todo list
3. **Add Tasks**: Create tasks with priorities, projects, and contexts
4. **Manage Tasks**: Edit, complete, delete, or bulk-process tasks
5. **Filter & Search**: Find tasks using the advanced filtering system
6. **Export/Import**: Download your todo.txt file or upload a new one
7. **Profile**: View statistics and manage your account

## Todo.txt Format

The application follows the standard todo.txt format:

```
(A) 2025-06-29 High priority task +Project @context
2025-06-29 Regular task +AnotherProject @home
x 2025-06-29 2025-06-28 Completed task +Project @context
```

- `(A)`, `(B)`, `(C)` - Priority levels
- `+Project` - Project tags
- `@context` - Context tags
- `x` - Completed tasks
- Dates in YYYY-MM-DD format

## Security

- Passwords are hashed using SHA-256
- Each user has isolated access to their own todo file
- Session management with Flask-Login
- No access to other users' data

## Development

The application uses:
- **Flask** - Web framework
- **Flask-Login** - User session management
- **Bootstrap 5** - UI framework (with custom terminal styling)
- **JSON** - User data storage
- **Plain text** - Todo.txt file format

## File Structure

```
├── app.py                 # Main Flask application
├── user_manager.py        # User authentication and management
├── todo_parser.py         # Todo.txt file parsing and manipulation
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html         # Base template with navigation
│   ├── login.html        # Login page
│   ├── register.html     # Registration page
│   ├── profile.html      # User profile page
│   ├── index.html        # Main task dashboard
│   ├── add_task.html     # Add task form
│   └── edit_task.html    # Edit task form
├── static/
│   ├── css/style.css     # Terminal-style CSS
│   └── js/app.js         # JavaScript functionality
├── users.json            # User account data
└── todo_*.txt            # Individual user todo files
```

## License

This project is open source and available under the MIT License.
