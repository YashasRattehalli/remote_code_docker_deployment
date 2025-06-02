from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # API Settings
    app_name: str = "Remote Code Docker Deployment API"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Docker Settings
    docker_base_image: str = "ubuntu:22.04"
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False


# Global settings instance
settings = Settings() 