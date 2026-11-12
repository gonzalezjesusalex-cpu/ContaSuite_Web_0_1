"""Provider contracts. A readable provider has no filesystem mutation methods."""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Protocol


class StorageError(Exception):
    """Only stable codes cross the service boundary; OS messages may contain secrets."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class FileMetadata:
    key: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class ScanIssue:
    key: str
    code: str


@dataclass(frozen=True)
class Availability:
    state: str
    code: str | None = None


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    sha256: str
    media_type: str


class ReadProvider(Protocol):
    def availability(self) -> Availability: ...
    def enumerate(self) -> Iterator[FileMetadata | ScanIssue]: ...
    def metadata(self, key: str) -> FileMetadata: ...
    def open_read(self, key: str) -> AbstractContextManager[BinaryIO]: ...


class InternalWriter(Protocol):
    def put(self, stream: BinaryIO, name: str) -> StoredFile: ...
    def discard(self, key: str) -> None: ...
