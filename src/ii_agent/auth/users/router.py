"""API routes for users domain."""

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.auth.users.dependencies import UserServiceDep

router = APIRouter(prefix="/auth", tags=["Users"])


@router.patch("/me/language")
async def update_user_language(
    current_user: CurrentUser,
    db: DBSession,
    user_service: UserServiceDep,
    language: str,
) -> dict[str, str]:
    """Update user's preferred language."""
    await user_service.update_language(db, current_user, language)
    return {"message": "Language updated successfully", "language": language}


@router.delete("/me")
async def delete_user_account(
    current_user: CurrentUser,
    db: DBSession,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Soft delete user account by setting is_active to False."""
    await user_service.delete_user(db, current_user)
    return {"message": "Account deleted successfully"}
