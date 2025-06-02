from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import sys
from datetime import datetime

from app.core.config import settings
from app.services.docker_service import DockerService
from app.api.containers import router as containers_router
from app.api.health import router as health_router
from app.models.schemas import ErrorResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)

logger = logging.getLogger(__name__)

# Global Docker service instance
docker_service: DockerService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    Handles startup and shutdown events.
    """
    # Startup
    global docker_service
    logger.info("Starting Remote Code Docker Deployment API...")
    
    try:
        # Initialize Docker service
        docker_service = DockerService()
        await docker_service.initialize()
        logger.info("Docker service initialized successfully")
        
        # Store in app state for access in routes
        app.state.docker_service = docker_service
        
        logger.info(f"API startup completed. Service ready on {settings.host}:{settings.port}")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise RuntimeError(f"Service initialization failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Remote Code Docker Deployment API...")
    
    try:
        if docker_service:
            await docker_service.shutdown()
            logger.info("Docker service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    logger.info("API shutdown completed")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
    ## Remote Code Docker Deployment API
    
    A lightweight HTTP API for cloning GitHub repositories into Docker containers and executing commands.
    
    ### Features:
    
    * **Container Management**: Create, list, monitor, and destroy containers
    * **Repository Cloning**: Clone any public GitHub repository at specific branches/commits
    * **Command Execution**: Execute commands inside containers with security controls
    * **File System Access**: Browse directories and read file contents
    * **Automatic Cleanup**: Containers are automatically destroyed after expiration
    * **Health Monitoring**: Built-in health checks and service monitoring
    
    ### Use Cases:
    
    * Code analysis and testing
    * CI/CD pipeline integration
    * Parallel job execution
    * Sandboxed code execution
    * Repository inspection and auditing
    
    ### Security:
    
    * Command whitelist for security
    * Container resource limits
    * Automatic timeout and cleanup
    * File size limits for downloads
    """,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error format"""
    error_response = ErrorResponse(
        error=exc.detail,
        detail=getattr(exc, 'detail', None)
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(mode='json')
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    error_response = ErrorResponse(
        error="Internal server error",
        detail=str(exc) if settings.debug else "An unexpected error occurred"
    )
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(mode='json')
    )


# Include routers
app.include_router(containers_router, prefix="/docker/repo")
app.include_router(health_router, prefix="/docker/repo")


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_url": "/docker/repo/health"
    }


# Additional metadata endpoints
@app.get("/docker/repo/info", tags=["info"])
async def api_info():
    """
    Get API configuration and limits information.
    """
    return {
        "api_name": settings.app_name,
        "api_version": settings.app_version,
        "docker": {
            "base_image": settings.docker_base_image
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    ) 