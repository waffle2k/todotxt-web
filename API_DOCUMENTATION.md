# Todo.txt REST API Documentation

This document describes the REST API endpoints for the Todo.txt Web Manager that provide import and export functionality using basic authentication.

## Authentication

All API endpoints require HTTP Basic Authentication using your username and password from the web application.

## Base URL

```
http://localhost:5000/api/v1
```

## Endpoints

### 1. GET /api/v1/todo

**Description:** Export/retrieve the current user's todo.txt file content.

**Method:** GET

**Authentication:** Basic Auth required

**Response:** Plain text content of the todo.txt file

**Example:**
```bash
curl -X GET http://localhost:5000/api/v1/todo -u "username:password"
```

**Response Example:**
```
(A) 2025-06-30 Test API task via REST +API @testing
(B) 2025-06-30 Another task from API +Development @computer
2025-06-30 Simple task without priority +General @anywhere
```

### 2. POST /api/v1/todo

**Description:** Import/update the current user's todo.txt file content.

**Method:** POST

**Authentication:** Basic Auth required

**Content Types Supported:**
- `text/plain` - Send todo.txt content directly in request body
- `application/json` - Send JSON with `content` field

**Response:** JSON with success status and statistics

**Example with plain text:**
```bash
curl -X POST http://localhost:5000/api/v1/todo \
  -u "username:password" \
  -H "Content-Type: text/plain" \
  -d "(A) 2025-06-30 New task +Project @context
(B) 2025-06-30 Another task +Work @office"
```

**Example with JSON:**
```bash
curl -X POST http://localhost:5000/api/v1/todo \
  -u "username:password" \
  -H "Content-Type: application/json" \
  -d '{"content": "(A) 2025-06-30 New task +Project @context\n(B) 2025-06-30 Another task +Work @office"}'
```

**Response Example:**
```json
{
  "success": true,
  "message": "Todo file updated successfully",
  "username": "apitest",
  "statistics": {
    "total_tasks": 3,
    "completed_tasks": 1,
    "incomplete_tasks": 2
  }
}
```

### 3. GET /api/v1/todo/info

**Description:** Get detailed information and statistics about the user's todo file.

**Method:** GET

**Authentication:** Basic Auth required

**Response:** JSON with statistics, projects, and contexts

**Example:**
```bash
curl -X GET http://localhost:5000/api/v1/todo/info -u "username:password"
```

**Response Example:**
```json
{
  "username": "apitest",
  "statistics": {
    "total_tasks": 3,
    "completed_tasks": 1,
    "incomplete_tasks": 2,
    "priority_distribution": {
      "A": 1,
      "B": 0,
      "C": 1,
      "None": 0
    },
    "total_projects": 3,
    "total_contexts": 3
  },
  "projects": ["development", "done", "json"],
  "contexts": ["anywhere", "home", "testing"]
}
```

## Error Responses

### 401 Unauthorized
```
Authentication required
```
or
```
Invalid credentials
```

### 400 Bad Request
```json
{
  "error": "Bad request",
  "message": "JSON payload must contain 'content' field"
}
```

### 404 Not Found
```json
{
  "error": "Todo file not found",
  "message": "User todo file does not exist"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error",
  "message": "Error description"
}
```

## Usage Examples

### Backup your todo.txt file
```bash
curl -X GET http://localhost:5000/api/v1/todo -u "myuser:mypass" > backup.txt
```

### Restore from backup
```bash
curl -X POST http://localhost:5000/api/v1/todo -u "myuser:mypass" \
  -H "Content-Type: text/plain" \
  --data-binary @backup.txt
```

### Get statistics
```bash
curl -X GET http://localhost:5000/api/v1/todo/info -u "myuser:mypass" | jq .
```

## Integration with Todo.txt Format

The API fully supports the todo.txt format including:
- Priority levels: (A), (B), (C)
- Projects: +ProjectName
- Contexts: @ContextName
- Completion dates: x 2025-06-30
- Creation dates: 2025-06-30

## Security Notes

- Always use HTTPS in production environments
- Store credentials securely
- Consider using environment variables for credentials in scripts
- The API uses the same authentication as the web interface

## Rate Limiting

Currently, no rate limiting is implemented. Use responsibly.
