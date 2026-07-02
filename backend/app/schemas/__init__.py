from pydantic import BaseModel


class Msg(BaseModel):
    """Simple message response schema."""
    msg: str


class HealthCheck(BaseModel):
    """Health check endpoint response schema."""
    status: str
    version: str
    database: str
    redis: str
