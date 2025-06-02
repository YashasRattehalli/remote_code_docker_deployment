import docker
import asyncio
import logging
import time
import tempfile
import shutil
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from docker.models.containers import Container
from docker.errors import DockerException, NotFound, APIError

from app.core.config import settings
from app.models.schemas import (
    ContainerStatus, ContainerResponse, CommandResponse,
    FileSystemItem, BrowseDirectoryResponse, FileContentResponse
)


logger = logging.getLogger(__name__)


class ContainerInfo:
    def __init__(self, container_id: str, repo_url: str, branch: str, commit: Optional[str],
                 created_at: datetime, expires_at: Optional[datetime], working_directory: str):
        self.container_id = container_id
        self.repo_url = repo_url
        self.branch = branch
        self.commit = commit
        self.created_at = created_at
        self.expires_at = expires_at
        self.working_directory = working_directory
        self.status = ContainerStatus.CREATING
        self.docker_container: Optional[Container] = None


class DockerService:
    def __init__(self):
        self.client = None
        self.containers: Dict[str, ContainerInfo] = {}
        self._cleanup_task = None
        self._start_time = datetime.utcnow()
        
    async def initialize(self):
        """Initialize Docker client and start cleanup task"""
        try:
            self.client = docker.from_env()
            # Test Docker connection
            self.client.ping()
            logger.info("Docker client initialized successfully")
            
            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_containers())
            
        except DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise RuntimeError(f"Docker service unavailable: {e}")
    
    async def shutdown(self):
        """Shutdown service and cleanup resources"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup all managed containers
        for container_info in list(self.containers.values()):
            await self._destroy_container(container_info.container_id)
    
    def is_docker_available(self) -> bool:
        """Check if Docker daemon is available"""
        try:
            if self.client:
                self.client.ping()
                return True
        except Exception:
            pass
        return False
    
    async def create_container(self, repo_url: str, branch: Optional[str] = None,
                              commit: Optional[str] = None, max_runtime_secs: int = None,
                              environment_vars: Optional[Dict[str, str]] = None,
                              initial_command: Optional[str] = None) -> ContainerResponse:
        """Create and start a new container with cloned repository"""
        
        # Generate unique container ID
        container_id = f"repo-container-{int(time.time())}-{len(self.containers)}"
        
        # Handle branch/commit logic:
        # - If both empty: main branch, latest commit
        # - If branch only: specified branch, latest commit  
        # - If commit only: main branch, specific commit
        # - If both specified: specified branch, specific commit
        actual_branch = branch or "main"
        
        created_at = datetime.utcnow()
        
        # If user specifies runtime, set expiration; otherwise run indefinitely
        if max_runtime_secs:
            expires_at = created_at + timedelta(seconds=max_runtime_secs)
        else:
            expires_at = None  # No expiration
            
        working_directory = "/workspace"
        
        # Create container info
        container_info = ContainerInfo(
            container_id=container_id,
            repo_url=repo_url,
            branch=actual_branch,
            commit=commit,
            created_at=created_at,
            expires_at=expires_at,
            working_directory=working_directory
        )
        
        self.containers[container_id] = container_info
        
        try:
            # Create and start Docker container
            await self._create_docker_container(container_info, environment_vars, initial_command)
            container_info.status = ContainerStatus.RUNNING
            
        except Exception as e:
            container_info.status = ContainerStatus.FAILED
            logger.error(f"Failed to create container {container_id}: {e}")
            raise RuntimeError(f"Container creation failed: {e}")
        
        return self._container_info_to_response(container_info)
    
    async def _create_docker_container(self, container_info: ContainerInfo,
                                      environment_vars: Optional[Dict[str, str]] = None,
                                      initial_command: Optional[str] = None):
        """Create the actual Docker container"""
        
        # Prepare environment variables
        env_vars = environment_vars or {}
        env_vars.update({
            "REPO_URL": container_info.repo_url,
            "REPO_BRANCH": container_info.branch,
            "WORKING_DIR": container_info.working_directory
        })
        
        if container_info.commit:
            env_vars["REPO_COMMIT"] = container_info.commit
        
        # Create startup script
        startup_script = self._generate_startup_script(
            container_info.repo_url,
            container_info.branch,
            container_info.commit,
            container_info.working_directory,
            initial_command
        )
        
        try:
            # Create container without limits - let user control everything
            docker_container = self.client.containers.run(
                image=settings.docker_base_image,
                command=["bash", "-c", startup_script],
                detach=True,
                name=container_info.container_id,
                environment=env_vars,
                working_dir=container_info.working_directory,
                remove=False,  # We'll handle cleanup manually
                stdout=True,
                stderr=True
            )
            
            container_info.docker_container = docker_container
            logger.info(f"Container {container_info.container_id} created successfully")
            
        except DockerException as e:
            logger.error(f"Docker container creation failed: {e}")
            raise
    
    def _generate_startup_script(self, repo_url: str, branch: str, commit: Optional[str],
                                working_dir: str, initial_command: Optional[str] = None) -> str:
        """Generate the startup script for the container"""
        
        script_lines = [
            "#!/bin/bash",
            "set -e",
            "",
            "# Update system and install dependencies",
            "apt-get update -qq",
            "apt-get install -y -qq git curl wget python3 python3-pip nodejs npm tree",
            "",
            f"# Create working directory",
            f"mkdir -p {working_dir}",
            f"cd {working_dir}",
            "",
            "# Clone repository",
            f"echo 'Cloning repository: {repo_url}'",
            f"git clone {repo_url} .",
            "",
        ]
        
        # Handle branch and commit logic
        if commit:
            # If commit is specified, checkout that specific commit
            script_lines.extend([
                f"# Checkout specific commit: {commit}",
                f"git checkout {commit}",
            ])
        else:
            # If no commit specified, try to checkout the branch with fallbacks
            script_lines.extend([
                f"# Attempt to checkout branch: {branch}",
                f"if git checkout {branch} 2>/dev/null; then",
                f"    echo 'Successfully checked out branch: {branch}'",
                f"elif git checkout main 2>/dev/null; then",
                f"    echo 'Branch {branch} not found, using main branch instead'",
                f"elif git checkout master 2>/dev/null; then",
                f"    echo 'Branch {branch} and main not found, using master branch instead'",
                f"else",
                f"    echo 'Using default branch (could not find {branch}, main, or master)'",
                f"    # Just use whatever branch we're on after clone",
                f"fi",
            ])
        
        # Add initial command if provided
        if initial_command:
            script_lines.extend([
                "",
                "# Execute initial command",
                f"echo 'Executing initial command: {initial_command}'",
                initial_command,
            ])
        
        # Keep container alive
        script_lines.extend([
            "",
            "# Keep container alive",
            "echo 'Container ready. Repository cloned successfully.'",
            "tail -f /dev/null"
        ])
        
        return "\n".join(script_lines)
    
    async def execute_command(self, container_id: str, command: str,
                             working_directory: Optional[str] = None,
                             timeout_secs: int = 30) -> CommandResponse:
        """Execute a command in the specified container"""
        
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container_info = self.containers[container_id]
        
        if container_info.status != ContainerStatus.RUNNING:
            raise RuntimeError(f"Container {container_id} is not running (status: {container_info.status})")
        
        if not container_info.docker_container:
            raise RuntimeError(f"Docker container for {container_id} not found")
        
        start_time = time.time()
        
        try:
            # Prepare the command with working directory
            work_dir = working_directory or container_info.working_directory
            exec_command = f"cd {work_dir} && {command}"
            
            # Execute command
            exec_result = container_info.docker_container.exec_run(
                cmd=["bash", "-c", exec_command],
                stdout=True,
                stderr=True,
                demux=True,
                workdir=work_dir
            )
            
            execution_time = time.time() - start_time
            
            # Process output
            stdout = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
            stderr = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ""
            
            return CommandResponse(
                command=command,
                exit_code=exec_result.exit_code,
                stdout=stdout,
                stderr=stderr,
                execution_time_secs=round(execution_time, 3),
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Command execution failed in container {container_id}: {e}")
            
            return CommandResponse(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command execution failed: {str(e)}",
                execution_time_secs=round(execution_time, 3),
                timestamp=datetime.utcnow()
            )
    
    async def browse_directory(self, container_id: str, path: str = "/") -> BrowseDirectoryResponse:
        """Browse directory contents in the container"""
        
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container_info = self.containers[container_id]
        
        if container_info.status != ContainerStatus.RUNNING:
            raise RuntimeError(f"Container {container_id} is not running")
        
        # Use ls command to get directory contents
        ls_command = f"ls -la {path}"
        result = await self.execute_command(container_id, ls_command, timeout_secs=10)
        
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to browse directory {path}: {result.stderr}")
        
        # Parse ls output
        items = []
        lines = result.stdout.strip().split('\n')[1:]  # Skip the first line (total)
        
        for line in lines:
            if not line.strip():
                continue
                
            parts = line.split()
            if len(parts) < 9:
                continue
                
            permissions = parts[0]
            size = int(parts[4]) if parts[4].isdigit() else None
            name = ' '.join(parts[8:])
            
            # Skip . and .. entries
            if name in ['.', '..']:
                continue
            
            item_type = "directory" if permissions.startswith('d') else "file"
            
            items.append(FileSystemItem(
                name=name,
                type=item_type,
                size=size if item_type == "file" else None,
                permissions=permissions
            ))
        
        return BrowseDirectoryResponse(
            path=path,
            items=items,
            total_items=len(items)
        )
    
    async def get_file_content(self, container_id: str, file_path: str) -> FileContentResponse:
        """Get file content from the container"""
        
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container_info = self.containers[container_id]
        
        if container_info.status != ContainerStatus.RUNNING:
            raise RuntimeError(f"Container {container_id} is not running")
        
        # Check if file exists and get size
        stat_result = await self.execute_command(container_id, f"stat -c '%s' {file_path}", timeout_secs=10)
        
        if stat_result.exit_code != 0:
            raise ValueError(f"File {file_path} not found or not accessible")
        
        file_size = int(stat_result.stdout.strip())
        
        # Get file content
        cat_result = await self.execute_command(container_id, f"cat {file_path}", timeout_secs=30)
        
        if cat_result.exit_code != 0:
            raise RuntimeError(f"Failed to read file {file_path}: {cat_result.stderr}")
        
        # Check if file is binary
        content = cat_result.stdout
        is_binary = '\x00' in content
        
        return FileContentResponse(
            path=file_path,
            content=content,
            size=file_size,
            encoding="utf-8",
            is_binary=is_binary
        )
    
    async def get_container_status(self, container_id: str) -> ContainerResponse:
        """Get container status and information"""
        
        if container_id not in self.containers:
            raise ValueError(f"Container {container_id} not found")
        
        container_info = self.containers[container_id]
        
        # Update status based on Docker container state
        if container_info.docker_container:
            try:
                container_info.docker_container.reload()
                docker_status = container_info.docker_container.status
                
                if docker_status == "running":
                    # Check if expired (only for containers with expiration)
                    if container_info.expires_at and datetime.utcnow() > container_info.expires_at:
                        container_info.status = ContainerStatus.TIMEOUT
                        await self._destroy_container(container_id)
                    else:
                        container_info.status = ContainerStatus.RUNNING
                elif docker_status in ["exited", "dead"]:
                    container_info.status = ContainerStatus.COMPLETED
                
            except NotFound:
                container_info.status = ContainerStatus.DESTROYED
        
        return self._container_info_to_response(container_info)
    
    async def list_containers(self) -> Dict[str, ContainerResponse]:
        """List all managed containers"""
        result = {}
        
        for container_id in list(self.containers.keys()):
            try:
                result[container_id] = await self.get_container_status(container_id)
            except Exception as e:
                logger.error(f"Error getting status for container {container_id}: {e}")
        
        return result
    
    async def destroy_container(self, container_id: str) -> bool:
        """Manually destroy a container"""
        return await self._destroy_container(container_id)
    
    async def _destroy_container(self, container_id: str) -> bool:
        """Internal method to destroy a container"""
        
        if container_id not in self.containers:
            return False
        
        container_info = self.containers[container_id]
        
        try:
            if container_info.docker_container:
                # Stop and remove the container
                container_info.docker_container.stop(timeout=10)
                container_info.docker_container.remove(force=True)
                logger.info(f"Container {container_id} destroyed successfully")
            
            container_info.status = ContainerStatus.DESTROYED
            del self.containers[container_id]
            return True
            
        except Exception as e:
            logger.error(f"Error destroying container {container_id}: {e}")
            container_info.status = ContainerStatus.FAILED
            return False
    
    async def _cleanup_expired_containers(self):
        """Background task to cleanup expired containers"""
        
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                current_time = datetime.utcnow()
                expired_containers = []
                
                for container_id, container_info in self.containers.items():
                    # Only cleanup containers that have expiration times
                    if container_info.expires_at and current_time > container_info.expires_at:
                        expired_containers.append(container_id)
                
                for container_id in expired_containers:
                    logger.info(f"Cleaning up expired container: {container_id}")
                    await self._destroy_container(container_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    def _container_info_to_response(self, container_info: ContainerInfo) -> ContainerResponse:
        """Convert ContainerInfo to ContainerResponse"""
        return ContainerResponse(
            container_id=container_info.container_id,
            status=container_info.status,
            repo_url=container_info.repo_url,
            branch=container_info.branch,
            commit=container_info.commit,
            created_at=container_info.created_at,
            expires_at=container_info.expires_at,
            working_directory=container_info.working_directory
        )
    
    def get_service_stats(self) -> Dict[str, any]:
        """Get service statistics"""
        active_containers = sum(1 for info in self.containers.values() 
                               if info.status == ContainerStatus.RUNNING)
        
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "total_containers": len(self.containers),
            "active_containers": active_containers,
            "docker_available": self.is_docker_available()
        } 