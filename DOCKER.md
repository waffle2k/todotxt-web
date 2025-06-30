# Docker Deployment Guide

This Todo.txt Web Manager application includes multiple Docker Compose configurations for different use cases.

## Available Docker Compose Files

### 1. `docker-compose.yml` (Basic)
Simple configuration for quick testing and basic deployment.

### 2. `docker-compose.prod.yml` (Production)
Enhanced production-ready configuration with security hardening and resource limits.

### 3. `docker-compose.dev.yml` (Development)
Development configuration with live code reloading and debugging enabled.

## Quick Start

### Basic Deployment
```bash
# Start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

### Production Deployment
```bash
# Set a secure secret key
export SECRET_KEY="your-very-secure-random-secret-key-here"

# Start production environment
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop production environment
docker-compose -f docker-compose.prod.yml down
```

### Development Environment
```bash
# Start development environment with live reload
docker-compose -f docker-compose.dev.yml up -d

# View logs (will show Flask debug output)
docker-compose -f docker-compose.dev.yml logs -f

# Stop development environment
docker-compose -f docker-compose.dev.yml down
```

## Configuration Details

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `FLASK_ENV` | Flask environment mode | `production` | No |
| `FLASK_APP` | Flask application file | `app.py` | No |
| `FLASK_DEBUG` | Enable Flask debug mode | `0` | No |
| `TODO_FILES_DIR` | Directory for user todo files | `/app/data` | No |
| `SECRET_KEY` | Flask secret key for sessions | Generated | **Yes for production** |

### Volume Mounts

- **Production**: `todo_data` volume mounted to `/app/data`
- **Development**: Source code mounted for live editing + separate data volume
- **Basic**: Simple named volume for data persistence

### Port Mapping

All configurations expose the application on port `5000`:
- Access via: `http://localhost:5000`

## Production Security Features

The production configuration includes:

- **Resource Limits**: CPU and memory constraints
- **Security Options**: No new privileges, read-only root filesystem
- **Health Checks**: Automatic container health monitoring
- **Restart Policy**: Automatic restart on failure
- **Secure Defaults**: Production environment variables

## Data Persistence

User data and todo files are stored in Docker volumes:

- **Basic/Dev**: Named volumes managed by Docker
- **Production**: Bind mount to `./data` directory for easier backup

## Backup and Restore

### Backup User Data
```bash
# Create backup directory
mkdir -p backups

# Copy data from container
docker cp todo-txt-manager:/app/data ./backups/todo-data-$(date +%Y%m%d)
```

### Restore User Data
```bash
# Copy backup to container
docker cp ./backups/todo-data-20231201 todo-txt-manager:/app/data
```

## Troubleshooting

### Check Container Status
```bash
docker-compose ps
```

### View Application Logs
```bash
docker-compose logs todo-app
```

### Access Container Shell
```bash
docker-compose exec todo-app /bin/bash
```

### Reset Data
```bash
# Stop containers
docker-compose down

# Remove data volume
docker volume rm todo_data

# Restart
docker-compose up -d
```

## Health Monitoring

All configurations include health checks that verify the application is responding:

- **Endpoint**: `http://localhost:5000/login`
- **Interval**: Every 30 seconds
- **Timeout**: 10 seconds
- **Retries**: 3 attempts

## Development Workflow

1. **Start Development Environment**:
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

2. **Make Code Changes**: Edit files directly - changes are reflected immediately

3. **View Logs**: Monitor Flask debug output
   ```bash
   docker-compose -f docker-compose.dev.yml logs -f
   ```

4. **Test Changes**: Access `http://localhost:5000`

5. **Stop When Done**:
   ```bash
   docker-compose -f docker-compose.dev.yml down
   ```

## Production Deployment Checklist

- [ ] Set secure `SECRET_KEY` environment variable
- [ ] Configure proper backup strategy for `./data` directory
- [ ] Set up reverse proxy (nginx/Apache) if needed
- [ ] Configure SSL/TLS certificates
- [ ] Set up log rotation and monitoring
- [ ] Test health check endpoints
- [ ] Verify resource limits are appropriate

## Access the Application

Once running, access your Todo.txt Web Manager at:
- **URL**: `http://localhost:5000`
- **Features**: Green monochrome monitor interface
- **Authentication**: Register new users or login with existing accounts
