import json
import hashlib
import os
from datetime import datetime
from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, username, email, password_hash=None):
        self.id = username
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.created_at = datetime.now().isoformat()
        self.last_login = None
    
    def check_password(self, password):
        """Check if provided password matches the stored hash"""
        return self.password_hash == self._hash_password(password)
    
    def set_password(self, password):
        """Set password by hashing it"""
        self.password_hash = self._hash_password(password)
    
    @staticmethod
    def _hash_password(password):
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    def to_dict(self):
        """Convert user to dictionary for JSON storage"""
        return {
            'username': self.username,
            'email': self.email,
            'password_hash': self.password_hash,
            'created_at': self.created_at,
            'last_login': self.last_login
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create user from dictionary"""
        user = cls(data['username'], data['email'], data['password_hash'])
        user.created_at = data.get('created_at', datetime.now().isoformat())
        user.last_login = data.get('last_login')
        return user

class UserManager:
    def __init__(self, users_file='users.json', todo_dir=None):
        # Configure todo files directory from environment variable or default to current directory
        if todo_dir is None:
            self.todo_dir = os.environ.get('TODO_FILES_DIR', os.getcwd())
        else:
            self.todo_dir = todo_dir
        
        # Store users.json in the same directory as todo data files
        self.users_file = os.path.join(self.todo_dir, users_file)
        self.users = {}
        
        # Ensure the todo directory exists
        os.makedirs(self.todo_dir, exist_ok=True)
        
        self.load_users()
    
    def load_users(self):
        """Load users from JSON file"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    users_data = json.load(f)
                    for username, user_data in users_data.items():
                        self.users[username] = User.from_dict(user_data)
            except (json.JSONDecodeError, KeyError):
                # If file is corrupted, start fresh
                self.users = {}
    
    def save_users(self):
        """Save users to JSON file"""
        users_data = {}
        for username, user in self.users.items():
            users_data[username] = user.to_dict()
        
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=2, ensure_ascii=False)
    
    def create_user(self, username, email, password):
        """Create a new user"""
        if username in self.users:
            return None, "Username already exists"
        
        if self.get_user_by_email(email):
            return None, "Email already registered"
        
        # Validate input
        if not username or not email or not password:
            return None, "All fields are required"
        
        if len(username) < 3:
            return None, "Username must be at least 3 characters"
        
        if len(password) < 6:
            return None, "Password must be at least 6 characters"
        
        if '@' not in email:
            return None, "Invalid email address"
        
        # Create user
        user = User(username, email)
        user.set_password(password)
        self.users[username] = user
        self.save_users()
        
        # Create user's todo file
        self.create_user_todo_file(username)
        
        return user, "User created successfully"
    
    def authenticate_user(self, username, password):
        """Authenticate user with username and password"""
        user = self.users.get(username)
        if user and user.check_password(password):
            # Update last login
            user.last_login = datetime.now().isoformat()
            self.save_users()
            return user
        return None
    
    def get_user(self, username):
        """Get user by username"""
        return self.users.get(username)
    
    def get_user_by_email(self, email):
        """Get user by email"""
        for user in self.users.values():
            if user.email == email:
                return user
        return None
    
    def create_user_todo_file(self, username):
        """Create a todo.txt file for the user"""
        user_todo_file = os.path.join(self.todo_dir, f"todo_{username}.txt")
        if not os.path.exists(user_todo_file):
            # Create with sample tasks
            sample_tasks = [
                f"(A) {datetime.now().strftime('%Y-%m-%d')} Welcome to your personal todo.txt manager! +Welcome @computer",
                f"{datetime.now().strftime('%Y-%m-%d')} Add your first task +GettingStarted @anywhere",
                f"(B) {datetime.now().strftime('%Y-%m-%d')} Explore the filtering and search features +Tutorial @computer"
            ]
            
            with open(user_todo_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(sample_tasks) + '\n')
    
    def get_user_todo_file(self, username):
        """Get the todo file path for a user"""
        return os.path.join(self.todo_dir, f"todo_{username}.txt")
    
    def delete_user(self, username):
        """Delete a user and their todo file"""
        if username in self.users:
            # Delete user's todo file
            user_todo_file = self.get_user_todo_file(username)
            if os.path.exists(user_todo_file):
                os.remove(user_todo_file)
            
            # Remove user
            del self.users[username]
            self.save_users()
            return True
        return False
    
    def get_user_stats(self):
        """Get statistics about users"""
        return {
            'total_users': len(self.users),
            'users_with_recent_login': len([u for u in self.users.values() if u.last_login]),
            'newest_user': max(self.users.values(), key=lambda u: u.created_at).username if self.users else None
        }
    
    def get_todo_directory(self):
        """Get the configured todo files directory"""
        return self.todo_dir
    
    def get_user_todo_file_display_path(self, username):
        """Get a display-friendly path for the user's todo file"""
        full_path = self.get_user_todo_file(username)
        # If it's in the current directory, show relative path
        if self.todo_dir == os.getcwd():
            return f"./todo_{username}.txt"
        else:
            return full_path
