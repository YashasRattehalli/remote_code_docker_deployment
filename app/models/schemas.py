from pydantic import BaseModel, HttpUrl, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ContainerStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    DESTROYED = "destroyed"


class CreateContainerRequest(BaseModel):
    repo_url: HttpUrl = Field(..., description="GitHub repository URL")
    branch: Optional[str] = Field(None, description="Branch name (optional, defaults to 'main', can be omitted even when commit is specified)")
    commit: Optional[str] = Field(None, description="Specific commit hash (optional, can be used with or without branch)")
    max_runtime_secs: Optional[int] = Field(None, description="Maximum runtime in seconds (optional, no expiration if not specified)")
    environment_vars: Optional[Dict[str, str]] = Field(default_factory=dict, description="Environment variables")
    initial_command: Optional[str] = Field(None, description="Initial command to run after cloning")
    
    @validator('repo_url')
    def validate_github_url(cls, v):
        url_str = str(v)
        if not any(domain in url_str for domain in ['github.com', 'github.io']):
            raise ValueError('Only GitHub URLs are supported')
        return v


class ContainerResponse(BaseModel):
    container_id: str = Field(..., description="Unique container identifier")
    status: ContainerStatus = Field(..., description="Current container status")
    repo_url: str = Field(..., description="Repository URL")
    branch: str = Field(..., description="Branch being used")
    commit: Optional[str] = Field(None, description="Specific commit hash")
    created_at: datetime = Field(..., description="Container creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Container expiration timestamp (null if no expiration)")
    working_directory: str = Field(..., description="Working directory inside container")


class ExecuteCommandRequest(BaseModel):
    command: str = Field(..., description="Command to execute")
    working_directory: Optional[str] = Field(None, description="Working directory for command execution")
    timeout_secs: Optional[int] = Field(30, description="Command timeout in seconds")


class CommandResponse(BaseModel):
    command: str = Field(..., description="Executed command")
    exit_code: int = Field(..., description="Command exit code")
    stdout: str = Field(..., description="Standard output")
    stderr: str = Field(..., description="Standard error")
    execution_time_secs: float = Field(..., description="Execution time in seconds")
    timestamp: datetime = Field(..., description="Execution timestamp")


class FileSystemItem(BaseModel):
    name: str = Field(..., description="File or directory name")
    type: str = Field(..., description="Type: 'file' or 'directory'")
    size: Optional[int] = Field(None, description="File size in bytes (null for directories)")
    modified_at: Optional[datetime] = Field(None, description="Last modification time")
    permissions: Optional[str] = Field(None, description="File permissions")


class BrowseDirectoryResponse(BaseModel):
    path: str = Field(..., description="Directory path")
    items: List[FileSystemItem] = Field(..., description="Directory contents")
    total_items: int = Field(..., description="Total number of items")


class FileContentResponse(BaseModel):
    path: str = Field(..., description="File path")
    content: str = Field(..., description="File content")
    size: int = Field(..., description="File size in bytes")
    encoding: str = Field("utf-8", description="File encoding")
    is_binary: bool = Field(False, description="Whether file is binary")


class ContainerListResponse(BaseModel):
    containers: List[ContainerResponse] = Field(..., description="List of containers")
    total_count: int = Field(..., description="Total number of containers")
    active_count: int = Field(..., description="Number of active containers")


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Service health status")
    version: str = Field(..., description="API version")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    active_containers: int = Field(..., description="Number of active containers")
    docker_available: bool = Field(..., description="Docker daemon availability") 