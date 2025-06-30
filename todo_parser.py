import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class TodoTask:
    def __init__(self, line: str, line_number: int = 0):
        self.line_number = line_number
        self.raw_line = line.strip()
        self.completed = False
        self.priority = None
        self.completion_date = None
        self.creation_date = None
        self.description = ""
        self.projects = []
        self.contexts = []
        self.key_values = {}
        
        self._parse_line()
    
    def _parse_line(self):
        """Parse a todo.txt line into its components"""
        line = self.raw_line
        
        # Check if completed
        if line.startswith('x '):
            self.completed = True
            line = line[2:]  # Remove 'x '
            
            # Try to extract completion date
            date_match = re.match(r'^(\d{4}-\d{2}-\d{2})\s+', line)
            if date_match:
                self.completion_date = date_match.group(1)
                line = line[len(date_match.group(0)):]
        
        # Extract priority
        priority_match = re.match(r'^\(([A-Z])\)\s+', line)
        if priority_match:
            self.priority = priority_match.group(1)
            line = line[len(priority_match.group(0)):]
        
        # Extract creation date
        date_match = re.match(r'^(\d{4}-\d{2}-\d{2})\s+', line)
        if date_match:
            self.creation_date = date_match.group(1)
            line = line[len(date_match.group(0)):]
        
        # Extract projects (+project)
        self.projects = re.findall(r'\+(\w+)', line)
        
        # Extract contexts (@context)
        self.contexts = re.findall(r'@(\w+)', line)
        
        # Extract key:value pairs
        kv_matches = re.findall(r'(\w+):(\w+)', line)
        self.key_values = dict(kv_matches)
        
        # The remaining text is the description
        self.description = line.strip()
    
    def get_clean_description(self) -> str:
        """Get description with projects and contexts stripped out"""
        clean_desc = self.description
        # Remove +project tags
        clean_desc = re.sub(r'\s*\+\w+', '', clean_desc)
        # Remove @context tags
        clean_desc = re.sub(r'\s*@\w+', '', clean_desc)
        # Clean up extra whitespace
        clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
        return clean_desc
    
    def to_string(self) -> str:
        """Convert task back to todo.txt format"""
        parts = []
        
        if self.completed:
            parts.append('x')
            if self.completion_date:
                parts.append(self.completion_date)
        
        if self.priority and not self.completed:
            parts.append(f'({self.priority})')
        
        if self.creation_date:
            parts.append(self.creation_date)
        
        parts.append(self.description)
        
        return ' '.join(parts)
    
    def matches_filter(self, search_term: str = "", priority_filter: str = "", 
                      project_filter: str = "", context_filter: str = "", 
                      completed_filter: str = "") -> bool:
        """Check if task matches the given filters"""
        
        # Search term filter
        if search_term and search_term.lower() not in self.description.lower():
            return False
        
        # Priority filter
        if priority_filter and priority_filter != "all":
            if priority_filter == "none" and self.priority:
                return False
            elif priority_filter != "none" and self.priority != priority_filter:
                return False
        
        # Project filter
        if project_filter and project_filter != "all":
            if project_filter not in self.projects:
                return False
        
        # Context filter
        if context_filter and context_filter != "all":
            if context_filter not in self.contexts:
                return False
        
        # Completed filter
        if completed_filter and completed_filter != "all":
            if completed_filter == "completed" and not self.completed:
                return False
            elif completed_filter == "incomplete" and self.completed:
                return False
        
        return True

class TodoParser:
    def __init__(self, filename: str = "todo.txt"):
        self.filename = filename
        self.tasks: List[TodoTask] = []
        self.load_tasks()
    
    def load_tasks(self):
        """Load tasks from the todo.txt file"""
        self.tasks = []
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if line:  # Skip empty lines
                        task = TodoTask(line, i)
                        self.tasks.append(task)
        except FileNotFoundError:
            # Create empty file if it doesn't exist
            with open(self.filename, 'w', encoding='utf-8') as f:
                pass
    
    def save_tasks(self):
        """Save all tasks back to the todo.txt file"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            for task in self.tasks:
                f.write(task.to_string() + '\n')
    
    def add_task(self, description: str, priority: str = None, 
                 projects: List[str] = None, contexts: List[str] = None) -> TodoTask:
        """Add a new task"""
        # Build the task string
        parts = []
        
        if priority:
            parts.append(f'({priority})')
        
        # Add creation date
        creation_date = datetime.now().strftime('%Y-%m-%d')
        parts.append(creation_date)
        
        # Add description
        task_desc = description
        
        # Add projects (filter out duplicates)
        if projects:
            unique_projects = list(dict.fromkeys(projects))  # Remove duplicates while preserving order
            for project in unique_projects:
                if not project.startswith('+'):
                    task_desc += f' +{project}'
                else:
                    task_desc += f' {project}'
        
        # Add contexts (filter out duplicates)
        if contexts:
            unique_contexts = list(dict.fromkeys(contexts))  # Remove duplicates while preserving order
            for context in unique_contexts:
                if not context.startswith('@'):
                    task_desc += f' @{context}'
                else:
                    task_desc += f' {context}'
        
        parts.append(task_desc)
        
        task_line = ' '.join(parts)
        new_task = TodoTask(task_line, len(self.tasks) + 1)
        self.tasks.append(new_task)
        self.save_tasks()
        return new_task
    
    def update_task(self, task_index: int, description: str, priority: str = None,
                   projects: List[str] = None, contexts: List[str] = None) -> bool:
        """Update an existing task"""
        if 0 <= task_index < len(self.tasks):
            task = self.tasks[task_index]
            
            # Build updated task string
            parts = []
            
            if task.completed:
                parts.append('x')
                if task.completion_date:
                    parts.append(task.completion_date)
            
            if priority and not task.completed:
                parts.append(f'({priority})')
            
            if task.creation_date:
                parts.append(task.creation_date)
            
            # Clean description by removing existing project and context tags to prevent duplicates
            clean_desc = description
            # Remove existing +project tags
            clean_desc = re.sub(r'\s*\+\w+', '', clean_desc)
            # Remove existing @context tags
            clean_desc = re.sub(r'\s*@\w+', '', clean_desc)
            # Clean up extra whitespace
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            
            task_desc = clean_desc
            
            # Add projects (filter out duplicates)
            if projects:
                unique_projects = list(dict.fromkeys(projects))  # Remove duplicates while preserving order
                for project in unique_projects:
                    if not project.startswith('+'):
                        task_desc += f' +{project}'
                    else:
                        task_desc += f' {project}'
            
            # Add contexts (filter out duplicates)
            if contexts:
                unique_contexts = list(dict.fromkeys(contexts))  # Remove duplicates while preserving order
                for context in unique_contexts:
                    if not context.startswith('@'):
                        task_desc += f' @{context}'
                    else:
                        task_desc += f' {context}'
            
            parts.append(task_desc)
            
            # Update the task
            updated_line = ' '.join(parts)
            self.tasks[task_index] = TodoTask(updated_line, task.line_number)
            self.save_tasks()
            return True
        return False
    
    def complete_task(self, task_index: int) -> bool:
        """Mark a task as completed"""
        if 0 <= task_index < len(self.tasks):
            task = self.tasks[task_index]
            if not task.completed:
                completion_date = datetime.now().strftime('%Y-%m-%d')
                completed_line = f"x {completion_date} {task.raw_line}"
                self.tasks[task_index] = TodoTask(completed_line, task.line_number)
                self.save_tasks()
                return True
        return False
    
    def uncomplete_task(self, task_index: int) -> bool:
        """Mark a task as incomplete"""
        if 0 <= task_index < len(self.tasks):
            task = self.tasks[task_index]
            if task.completed:
                # Remove completion marker and date
                line = task.raw_line
                if line.startswith('x '):
                    line = line[2:]
                    # Remove completion date if present
                    date_match = re.match(r'^\d{4}-\d{2}-\d{2}\s+', line)
                    if date_match:
                        line = line[len(date_match.group(0)):]
                
                self.tasks[task_index] = TodoTask(line, task.line_number)
                self.save_tasks()
                return True
        return False
    
    def delete_task(self, task_index: int) -> bool:
        """Delete a task"""
        if 0 <= task_index < len(self.tasks):
            del self.tasks[task_index]
            self.save_tasks()
            return True
        return False
    
    def get_all_projects(self) -> List[str]:
        """Get all unique projects from all tasks"""
        projects = set()
        for task in self.tasks:
            projects.update(task.projects)
        return sorted(list(projects))
    
    def get_all_contexts(self) -> List[str]:
        """Get all unique contexts from all tasks"""
        contexts = set()
        for task in self.tasks:
            contexts.update(task.contexts)
        return sorted(list(contexts))
    
    def get_filtered_tasks(self, search_term: str = "", priority_filter: str = "", 
                          project_filter: str = "", context_filter: str = "", 
                          completed_filter: str = "") -> List[Tuple[int, TodoTask]]:
        """Get tasks that match the given filters, with their indices, ordered by priority"""
        filtered = []
        for i, task in enumerate(self.tasks):
            if task.matches_filter(search_term, priority_filter, project_filter, 
                                 context_filter, completed_filter):
                filtered.append((i, task))
        
        # Sort by priority: A (highest) -> B -> C -> None (lowest), then by completion status
        def priority_sort_key(item):
            _, task = item
            # Completed tasks go to the end
            if task.completed:
                return (1, 'Z', task.line_number)  # Use 'Z' to put completed tasks last
            
            # Priority order: A=0, B=1, C=2, None=3
            priority_order = {'A': 0, 'B': 1, 'C': 2}
            priority_value = priority_order.get(task.priority, 3)
            
            return (0, priority_value, task.line_number)
        
        filtered.sort(key=priority_sort_key)
        return filtered
