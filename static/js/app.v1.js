// Todo.txt Web Manager JavaScript

// Global variables
let searchTimeout;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Initialize search functionality
    initializeSearch();
    
    // Initialize filter functionality
    initializeFilters();
    
    // Initialize task selection
    initializeTaskSelection();
    
    // Initialize keyboard shortcuts
    initializeKeyboardShortcuts();
    
    // Initialize tooltips if Bootstrap is available
    if (typeof bootstrap !== 'undefined') {
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

// Search functionality
function initializeSearch() {
    const searchInput = document.getElementById('search');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(function() {
                document.getElementById('filterForm').submit();
            }, 500);
        });
    }
}

// Filter functionality
function initializeFilters() {
    const filterElements = document.querySelectorAll('#priority, #project, #context, #completed');
    filterElements.forEach(function(element) {
        element.addEventListener('change', function() {
            document.getElementById('filterForm').submit();
        });
    });
}

// Task selection functionality
function initializeTaskSelection() {
    // Update selected count on page load
    updateSelectedCount();
    
    // Add event listeners to checkboxes
    const taskCheckboxes = document.querySelectorAll('.task-checkbox');
    taskCheckboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSelectedCount);
    });
    
    // Add event listener to select all checkbox
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', toggleAllTasks);
    }
}

// Keyboard shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl+/ or Cmd+/ - Focus search
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            const searchInput = document.getElementById('search');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }
        
        // Ctrl+N or Cmd+N - New task (if on main page)
        if ((e.ctrlKey || e.metaKey) && e.key === 'n' && window.location.pathname === '/') {
            e.preventDefault();
            window.location.href = '/add';
        }
        
        // Escape - Clear search
        if (e.key === 'Escape') {
            const searchInput = document.getElementById('search');
            if (searchInput && searchInput === document.activeElement) {
                searchInput.value = '';
                document.getElementById('filterForm').submit();
            }
        }
    });
}

// Task selection functions
function selectAllTasks() {
    const taskCheckboxes = document.querySelectorAll('.task-checkbox');
    taskCheckboxes.forEach(function(checkbox) {
        checkbox.checked = true;
    });
    document.getElementById('selectAllCheckbox').checked = true;
    updateSelectedCount();
}

function clearSelection() {
    const taskCheckboxes = document.querySelectorAll('.task-checkbox');
    taskCheckboxes.forEach(function(checkbox) {
        checkbox.checked = false;
    });
    document.getElementById('selectAllCheckbox').checked = false;
    updateSelectedCount();
}

function toggleAllTasks() {
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const taskCheckboxes = document.querySelectorAll('.task-checkbox');
    
    taskCheckboxes.forEach(function(checkbox) {
        checkbox.checked = selectAllCheckbox.checked;
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const selectedCount = document.querySelectorAll('.task-checkbox:checked').length;
    const countElement = document.getElementById('selectedCount');
    if (countElement) {
        countElement.textContent = selectedCount;
    }
    
    // Update select all checkbox state
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');
    const totalCheckboxes = document.querySelectorAll('.task-checkbox').length;
    
    if (selectAllCheckbox && totalCheckboxes > 0) {
        if (selectedCount === 0) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = false;
        } else if (selectedCount === totalCheckboxes) {
            selectAllCheckbox.indeterminate = false;
            selectAllCheckbox.checked = true;
        } else {
            selectAllCheckbox.indeterminate = true;
            selectAllCheckbox.checked = false;
        }
    }
}

// Bulk action confirmation
function confirmBulkAction() {
    const selectedCount = document.querySelectorAll('.task-checkbox:checked').length;
    const actionSelect = document.querySelector('select[name="action"]');
    
    if (selectedCount === 0) {
        alert('Please select at least one task.');
        return false;
    }
    
    if (!actionSelect || !actionSelect.value) {
        alert('Please select an action.');
        return false;
    }
    
    const action = actionSelect.value;
    let message = '';
    
    switch (action) {
        case 'complete':
            message = `Mark ${selectedCount} selected task(s) as complete?`;
            break;
        case 'uncomplete':
            message = `Mark ${selectedCount} selected task(s) as incomplete?`;
            break;
        case 'delete':
            message = `Delete ${selectedCount} selected task(s)? This action cannot be undone.`;
            break;
        default:
            message = `Apply "${action}" to ${selectedCount} selected task(s)?`;
    }
    
    return confirm(message);
}

// Task completion animation
function animateTaskCompletion(taskRow) {
    if (taskRow) {
        taskRow.classList.add('task-completed');
        setTimeout(function() {
            taskRow.classList.remove('task-completed');
        }, 300);
    }
}

// Form validation helpers
function validateForm(formElement) {
    let isValid = true;
    const requiredFields = formElement.querySelectorAll('[required]');
    
    requiredFields.forEach(function(field) {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
        }
    });
    
    return isValid;
}

// Loading state management
function setLoadingState(element, isLoading) {
    if (isLoading) {
        element.classList.add('loading');
        element.disabled = true;
    } else {
        element.classList.remove('loading');
        element.disabled = false;
    }
}

// Toast notifications (if needed)
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to page
    document.body.appendChild(toast);
    
    // Auto-remove after 5 seconds
    setTimeout(function() {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 5000);
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Export functions for use in templates
window.TodoApp = {
    selectAllTasks,
    clearSelection,
    toggleAllTasks,
    updateSelectedCount,
    confirmBulkAction,
    animateTaskCompletion,
    validateForm,
    setLoadingState,
    showToast
};
