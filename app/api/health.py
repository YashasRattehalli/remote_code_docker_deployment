from fastapi import APIRouter, Depends
import logging

from app.models.schemas import HealthResponse
from app.services.docker_service import DockerService
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


# Dependency to get Docker service instance
async def get_docker_service() -> DockerService:
    from app.main import docker_service
    return docker_service


@router.get("/", response_model=HealthResponse)
async def health_check(
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Health check endpoint that returns service status and statistics.
    """
    try:
        stats = docker_service.get_service_stats()
        
        return HealthResponse(
            status="healthy",
            version=settings.app_version,
            uptime_seconds=stats["uptime_seconds"],
            active_containers=stats["active_containers"],
            docker_available=stats["docker_available"]
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            version=settings.app_version,
            uptime_seconds=0,
            active_containers=0,
            docker_available=False
        )


@router.get("/ready")
async def readiness_check(
    docker_service: DockerService = Depends(get_docker_service)
):
    """
    Readiness check for load balancers and orchestration systems.
    """
    try:
        if docker_service.is_docker_available():
            return {"status": "ready"}
        else:
            return {"status": "not ready", "reason": "Docker unavailable"}, 503
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not ready", "reason": str(e)}, 503


@router.get("/live")
async def liveness_check():
    """
    Liveness check for orchestration systems.
    """
    return {"status": "alive"} 