from fastapi import APIRouter, HTTPException, Depends, Query, Path
from typing import Optional, Dict
import logging

from app.models.schemas import (
    CreateContainerRequest, ContainerResponse, ExecuteCommandRequest,
    CommandResponse, BrowseDirectoryResponse, FileContentResponse,
    ContainerListResponse, ErrorResponse
)
from app.services.docker_service import DockerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/containers", tags=["containers"])


# Dependency to get Docker service instance
async def get_docker_service() -> DockerService:
    from app.main import docker_service
    return docker_service


@router.post("/", response_model=ContainerResponse, status_code=201)
async def create_container(
    request: CreateContainerRequest,
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Create a new container with a cloned GitHub repository.
    
    - **repo_url**: GitHub repository URL
    - **branch**: Git branch (optional, defaults to 'main')
    - **commit**: Specific commit hash (optional, can be used with or without branch)
    - **max_runtime_secs**: Maximum container lifetime in seconds (optional, no expiration if not specified)
    - **environment_vars**: Environment variables for the container
    - **initial_command**: Command to run after repository cloning
    
    **Branch/Commit combinations:**
    - Both empty: uses 'main' branch with latest commit
    - Branch only: uses specified branch with latest commit
    - Commit only: uses 'main' branch with specific commit
    - Both specified: uses specified branch with specific commit
    """
    try:
        container = await docker_service.create_container(
            repo_url=str(request.repo_url),
            branch=request.branch,
            commit=request.commit,
            max_runtime_secs=request.max_runtime_secs,
            environment_vars=request.environment_vars,
            initial_command=request.initial_command
        )
        return container
    except Exception as e:
        logger.error(f"Container creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=ContainerListResponse)
async def list_containers(
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    List all managed containers with their current status.
    """
    try:
        containers_dict = await docker_service.list_containers()
        containers_list = list(containers_dict.values())
        
        active_count = sum(1 for c in containers_list if c.status == "running")
        
        return ContainerListResponse(
            containers=containers_list,
            total_count=len(containers_list),
            active_count=active_count
        )
    except Exception as e:
        logger.error(f"Failed to list containers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{container_id}", response_model=ContainerResponse)
async def get_container_status(
    container_id: str = Path(..., description="Container ID"),
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Get the status and details of a specific container.
    """
    try:
        container = await docker_service.get_container_status(container_id)
        return container
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get container status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{container_id}/execute", response_model=CommandResponse)
async def execute_command(
    container_id: str = Path(..., description="Container ID"),
    request: ExecuteCommandRequest = ...,
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Execute a command inside the specified container.
    
    - **command**: Command to execute
    - **working_directory**: Directory to run the command in (optional)
    - **timeout_secs**: Command timeout in seconds (1-300)
    """
    try:
        result = await docker_service.execute_command(
            container_id=container_id,
            command=request.command,
            working_directory=request.working_directory,
            timeout_secs=request.timeout_secs or 30
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{container_id}/browse", response_model=BrowseDirectoryResponse)
async def browse_directory(
    container_id: str = Path(..., description="Container ID"),
    path: str = Query("/workspace", description="Directory path to browse"),
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Browse the file system inside the container.
    
    - **path**: Directory path to browse (defaults to /workspace)
    """
    try:
        result = await docker_service.browse_directory(container_id, path)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Directory browsing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{container_id}/files", response_model=FileContentResponse)
async def get_file_content(
    container_id: str = Path(..., description="Container ID"),
    file_path: str = Query(..., description="File path to read"),
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Get the content of a file inside the container.
    
    - **file_path**: Path to the file to read
    """
    try:
        result = await docker_service.get_file_content(container_id, file_path)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"File reading failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{container_id}", status_code=204)
async def destroy_container(
    container_id: str = Path(..., description="Container ID"),
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Manually destroy a container before its expiration time.
    """
    try:
        success = await docker_service.destroy_container(container_id)
        if not success:
            raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        logger.error(f"Container destruction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 