from typing import Literal
from pydantic import BaseModel, Field


class ServicesHealth(BaseModel):
    """
    Sub-schema mapping status connection states of core database dependencies.
    """
    database: Literal["connected", "disconnected"] = Field(
        ..., description="PostgreSQL database connection state"
    )
    redis: Literal["connected", "disconnected"] = Field(
        ..., description="Redis cache/broker connection state"
    )


class HealthCheckResponse(BaseModel):
    """
    Detailed health check status response schema.
    """
    status: Literal["healthy", "unhealthy"] = Field(
        ..., description="Overall health state of the application"
    )
    version: str = Field(
        ..., description="Current running application software version"
    )
    environment: str = Field(
        ..., description="Active server execution runtime environment mode"
    )
    services: ServicesHealth = Field(
        ..., description="Details on status of external backing services"
    )
