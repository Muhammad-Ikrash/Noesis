from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    # Database record exists but the stored PDF file is gone.
    MISSING = "missing"


class ChunkKind(StrEnum):
    TEXT = "text"
    TABLE = "table"


class PageExtraction(StrEnum):
    TEXT = "text"
    # Reserved for a future OCR provider.
    OCR = "ocr"


class LearningMode(StrEnum):
    BASIC = "basic"
    EXTENSIVE = "extensive"


class RetrievalScope(StrEnum):
    # Only PDFs attached to this conversation.
    SESSION = "session"
    # Every completed PDF the student owns.
    LIBRARY = "library"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    NEEDS_CLARIFICATION = "needs_clarification"
    ERROR = "error"
