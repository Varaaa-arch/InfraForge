from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.schemas.response import ApiResponse
from app.services import project_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=ApiResponse[DashboardSummary])
def get_dashboard(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ApiResponse[DashboardSummary]:
    summary = DashboardSummary(
        projects=project_service.count_projects_for_owner(db, current_user.id),
        deployments=0,
        containers=0,
        servers=0,
    )
    return ApiResponse(data=summary)
