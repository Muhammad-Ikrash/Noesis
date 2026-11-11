from pydantic import BaseModel

from backend.models.enums import RetrievalScope


class UserSettings(BaseModel):
    default_retrieval_scope: RetrievalScope
