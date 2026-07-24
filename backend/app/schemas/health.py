from pydantic import BaseModel

class HealthStatus((BaseModel)):
    status: str

class ReadyStatus(BaseModel):
    status: str
    database: str
    redis: str

    