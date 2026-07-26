from pydantic import BaseModel


class DashboardSummary(BaseModel):
    projects: int
    deployments: int
    containers: int
    servers: int
