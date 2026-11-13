from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.server import ServerStatus
from app.models.user import User
from app.repositories import alert_repository
from app.schemas.dashboard import DashboardSummary
from app.schemas.response import ApiResponse
from app.services import application_service, container_service, deployment_service
from app.services import project_service, server_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ApiResponse[DashboardSummary]:
    projects = project_service.list_projects_for_owner(db, current_user.id)
    applications = application_service.list_applications_for_owner(
        db, [project.id for project in projects]
    )

    try:
        containers = container_service.list_containers(all_containers=True)
        containers_total = len(containers)
        containers_active = sum(1 for c in containers if c.status == "running")
    except RuntimeError:
        containers_total = 0
        containers_active = 0

    alerts = alert_repository.count_active_by_severity(db)

    summary = DashboardSummary(
        projects=len(projects),
        applications=len(applications),
        deployments=deployment_service.count_deployments_for_applications(
            db, [application.id for application in applications]
        ),
        servers=server_service.count_servers(db, current_user.id),
        servers_active=server_service.count_servers_by_status(
            db, current_user.id, ServerStatus.active
        ),
        servers_inactive=server_service.count_servers_by_status(
            db, current_user.id, ServerStatus.inactive
        ),
        servers_error=server_service.count_servers_by_status(
            db, current_user.id, ServerStatus.error
        ),
        containers=containers_active,
        containers_total=containers_total,
        alerts_active=sum(alerts.values()),
        alerts_critical=alerts.get("critical", 0),
        alerts_warning=alerts.get("warning", 0),
        alerts_info=alerts.get("info", 0),
        generated_at=datetime.now(tz=UTC),
    )
    return ApiResponse(data=summary)
