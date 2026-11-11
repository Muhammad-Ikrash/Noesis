"""Filesystem storage for uploaded PDFs. Keys are server-generated; user filenames never touch the path."""

import uuid
from pathlib import Path


class FileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_key() -> str:
        return f"{uuid.uuid4().hex}.pdf"

    def path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid storage key")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self.path_for(key)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)
