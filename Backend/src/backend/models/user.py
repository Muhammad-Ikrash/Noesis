from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base, Timestamps, UUIDPk
from backend.models.enums import RetrievalScope


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    # Nullable until authentication is implemented; the local user has none.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Default for new conversations: search only attached PDFs or the whole library.
    default_retrieval_scope: Mapped[RetrievalScope] = mapped_column(
        Enum(
            RetrievalScope,
            name="retrieval_scope",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RetrievalScope.SESSION,
    )
