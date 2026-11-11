from fastapi import APIRouter

from backend.api.dependencies import CurrentUser, DbSession
from backend.schemas.settings import UserSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
def get_user_settings(user: CurrentUser) -> UserSettings:
    return UserSettings(default_retrieval_scope=user.default_retrieval_scope)


@router.put("", response_model=UserSettings)
def update_user_settings(
    body: UserSettings, db: DbSession, user: CurrentUser
) -> UserSettings:
    """Default slider position for new chats: 'session' (this chat's PDFs) or 'library' (all PDFs)."""
    user.default_retrieval_scope = body.default_retrieval_scope
    db.commit()
    return UserSettings(default_retrieval_scope=user.default_retrieval_scope)
