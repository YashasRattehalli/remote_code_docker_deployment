# Remote Code Docker Deployment API

A lightweight HTTP API for cloning GitHub repositories into Docker containers and executing commands. Perfect for ad-hoc code analysis, testing, and parallel job execution in a sandboxed environment.

## Features

- 🐳 **Container Management**: Create, list, monitor, and destroy Docker containers
- 📦 **Repository Cloning**: Clone any public GitHub repository at specific branches/commits
- ⚡ **Command Execution**: Execute commands inside containers with security controls
- 📁 **File System Access**: Browse directories and read file contents
- 🔄 **Automatic Cleanup**: Containers are automatically destroyed after expiration
- 💚 **Health Monitoring**: Built-in health checks and service monitoring
- 🛡️ **Security**: Command whitelist, resource limits, and automatic timeouts

## Quick Start

### Prerequisites

- Python 3.9+
- Docker daemon running
- Git (for repository cloning)

### Installation

1. Clone this repository:

```bash
git clone https://github.com/yourusername/remote-code-docker-deployment.git
cd remote-code-docker-deployment
```

2. Install dependencies:

```bash
pip install -e .
```

3. Start the API:

```bash
python run.py
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for interactive documentation.

## API Endpoints

### Container Management

- `POST /api/v1/containers/` - Create a new container with cloned repository
- `GET /api/v1/containers/` - List all containers
- `GET /api/v1/containers/{container_id}` - Get container status
- `DELETE /api/v1/containers/{container_id}` - Destroy a container

### Command Execution

- `POST /api/v1/containers/{container_id}/execute` - Execute command in container

### File System

- `GET /api/v1/containers/{container_id}/browse` - Browse directory contents
- `GET /api/v1/containers/{container_id}/files` - Get file content

### Health & Info

- `GET /api/v1/health/` - Health check with statistics
- `GET /api/v1/health/ready` - Readiness check
- `GET /api/v1/health/live` - Liveness check
- `GET /api/v1/info` - API configuration and limits

## Usage Examples

### 1. Create a Container

```bash
# 1. Default: main branch, latest commit
curl -X POST "http://localhost:8000/api/v1/containers/" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/fastapi/fastapi"
  }'

# 2. Specific branch, latest commit
curl -X POST "http://localhost:8000/api/v1/containers/" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/fastapi/fastapi",
    "branch": "develop"
  }'

# 3. Main branch, specific commit
curl -X POST "http://localhost:8000/api/v1/containers/" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/fastapi/fastapi",
    "commit": "abc123def456"
  }'

# 4. Specific branch and commit
curl -X POST "http://localhost:8000/api/v1/containers/" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/fastapi/fastapi",
    "branch": "develop",
    "commit": "abc123def456"
  }'

# 5. With runtime limit (30 minutes)
curl -X POST "http://localhost:8000/api/v1/containers/" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/fastapi/fastapi",
    "max_runtime_secs": 1800
  }'
```

Response:

```json
{
  "container_id": "repo-container-1703123456-0",
  "status": "running",
  "repo_url": "https://github.com/fastapi/fastapi",
  "branch": "main",
  "commit": null,
  "created_at": "2023-12-21T10:30:56.123456",
  "expires_at": "2023-12-21T11:00:56.123456",
  "working_directory": "/workspace"
}
```

### 2. Execute Commands

```bash
curl -X POST "http://localhost:8000/api/v1/containers/repo-container-1703123456-0/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "python --version",
    "timeout_secs": 10
  }'
```

Response:

```json
{
  "command": "python --version",
  "exit_code": 0,
  "stdout": "Python 3.10.12\n",
  "stderr": "",
  "execution_time_secs": 0.045,
  "timestamp": "2023-12-21T10:31:15.789123"
}
```

### 3. Browse Directory

```bash
curl "http://localhost:8000/api/v1/containers/repo-container-1703123456-0/browse?path=/workspace"
```

### 4. Read File Content

```bash
curl "http://localhost:8000/api/v1/containers/repo-container-1703123456-0/files?file_path=/workspace/README.md"
```

### 5. List All Containers

```bash
curl "http://localhost:8000/api/v1/containers/"
```

## Configuration

The application can be configured via environment variables. Copy `example.env` to `.env` and modify as needed:

```bash
cp example.env .env
```

### Configuration Options

| Variable            | Default        | Description       |
| ------------------- | -------------- | ----------------- |
| `DEBUG`             | `false`        | Enable debug mode |
| `HOST`              | `0.0.0.0`      | API server host   |
| `PORT`              | `8000`         | API server port   |
| `DOCKER_BASE_IMAGE` | `ubuntu:22.04` | Base Docker image |

## Container Behavior

- **Runtime Control**: Containers run for the time specified in `max_runtime_secs` parameter
- **No Expiration**: If `max_runtime_secs` is not provided, containers run indefinitely until manually destroyed
- **No Restrictions**: Any command can be executed inside containers
- **Automatic Cleanup**: Only containers with expiration times are automatically cleaned up

## Security

The API provides a sandboxed environment with:

- **Container Isolation**: Each repository runs in its own Docker container
- **Network Isolation**: Containers are isolated from the host network
- **User Control**: Full control over container lifecycle and commands

## Development

### Project Structure

```
app/
├── __init__.py
├── main.py              # FastAPI application
├── api/                 # API routes
│   ├── containers.py    # Container management endpoints
│   └── health.py        # Health check endpoints
├── core/                # Core configuration
│   └── config.py        # Settings and configuration
├── models/              # Pydantic models
│   └── schemas.py       # Request/response schemas
└── services/            # Business logic
    └── docker_service.py # Docker container management
```

### Running in Development Mode

```bash
# Enable debug mode
export DEBUG=true

# Run with auto-reload
python run.py
```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    docker.io \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Copy application code
COPY app/ ./app/
COPY run.py ./

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "run.py"]
```

Build and run:

```bash
docker build -t remote-code-api .
docker run -p 8000:8000 -v /var/run/docker.sock:/var/run/docker.sock remote-code-api
```

## API Reference

### Request/Response Models

#### CreateContainerRequest

```json
{
  "repo_url": "https://github.com/owner/repo",
  "branch": "main",
  "commit": "abc123",
  "max_runtime_secs": 3600,
  "environment_vars": { "KEY": "value" },
  "initial_command": "echo 'Hello World'"
}
```

#### ExecuteCommandRequest

```json
{
  "command": "ls -la",
  "working_directory": "/workspace",
  "timeout_secs": 30
}
```

### Error Responses

All endpoints return consistent error responses:

```json
{
  "error": "Error message",
  "detail": "Detailed error information",
  "timestamp": "2023-12-21T10:30:56.123456"
}
```

## Monitoring

The API provides several monitoring endpoints:

- **Health Check**: `GET /api/v1/health/` - Service status and statistics
- **Readiness**: `GET /api/v1/health/ready` - Ready for traffic
- **Liveness**: `GET /api/v1/health/live` - Service is alive

### Metrics

The health endpoint returns:

- Service uptime
- Active container count
- Docker daemon status
- API version information

## Use Cases

- **Code Analysis**: Clone repositories and run static analysis tools
- **Testing**: Execute test suites in isolated environments
- **CI/CD Integration**: Parallel job execution for build pipelines
- **Code Auditing**: Inspect repository contents and structure
- **Educational**: Safe environment for running student code
- **Research**: Analyze large numbers of repositories

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and questions, please use the GitHub issue tracker.
