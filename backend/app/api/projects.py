from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_audit
from app.database.session import get_db
from app.models.project import Project, Visibility
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.response import ApiResponse 
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])

def _get_visible_project_or_404(db: Session, project_id: int, current_user: User) -> Project:
    project = project_service.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.owner_id != current_user.id and project.visibility != Visibility.public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project

def _get_owned_project_or_404(db: Session, project_id: int, current_user: User) -> Project:
    project = project_service.get_project_by_id(db, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if project.owner_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner of this project")
    return project

@router.post("", response_model=ApiResponse[ProjectResponse], status_code=status.HTTP_201_CREATED)
def create_project(
        payload: ProjectCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
) -> ApiResponse[ProjectResponse]:
    project = project_service.create_project(db, current_user.id, payload.name, payload.description, payload.visibility)
    log_audit("CREATE_PROJECT", user=current_user.username, project=project.slug)
    return ApiResponse(data=ProjectResponse.model_validate(project))

@router.get("", response_model=ApiResponse[list[ProjectResponse]])
def list_project(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ApiResponse[list[ProjectResponse]]:
    projects = project_service.list_project_for_owner(db, current_user.id)
    return ApiResponse(data=[ProjectResponse.model_validate(p) for p in projects])

@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
def get_project(
    project_id: int, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db), 
) -> ApiResponse[ProjectResponse]:
    project = _get_visible_project_or_404(db, project_id, current_user)
    return ApiResponse(data=ProjectResponse.model_validate(project))

@router.patch("/{project_id}", response_model=ApiResponse[ProjectResponse])
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[ProjectResponse]:
    project = _get_owned_project_or_404(db, project_id, current_user)
    updated = project_service.update_project(
        db,
        project, 
        name=payload.name,
        description=payload.description,
        visibility=payload.visibility,
    )
    log_audit("UPDATE_PROJECT", user=current_user.username, project=updated.slug)
    return ApiResponse(data=ProjectResponse.model_validate(updated))

@router.delete("/{project_id}", response_model=ApiResponse[MessageResponse])
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[MessageResponse]:
    project = _get_owned_project_or_404(db, project_id, current_user)
    slug = project.slug 
    project_service.delete_project(db, project)
    log_audit("DELETE_PROJECT", user=current_user.username, project=slug)
    return ApiResponse(data=MessageResponse(message="Project deleted successfully"))
 