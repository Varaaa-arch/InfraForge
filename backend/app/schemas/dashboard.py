from datetime import datetime

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    """Ringkasan global dashboard (resource user + status platform)."""

    projects: int
    applications: int
    deployments: int
    servers: int
    servers_active: int
    servers_inactive: int
    servers_error: int
    containers: int
    containers_total: int
    alerts_active: int
    alerts_critical: int
    alerts_warning: int
    alerts_info: int
    generated_at: datetime
