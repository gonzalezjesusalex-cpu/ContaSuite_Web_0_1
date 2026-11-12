"""Contract for future Python engines. Never import desktop GUI modules in FastAPI."""
from typing import Protocol
from pathlib import Path

class Engine(Protocol):
    def analyze(self, source: Path, options: dict) -> dict:
        """Return proposed changes without altering files."""
        ...
    def execute(self, plan: dict, destination: Path) -> dict:
        """Apply a reviewed plan, returning results and a journal for auditing."""
        ...

# Registration must be explicit. Do not accept shell commands, Python code or module names from API payloads.
ENGINES: dict[str, Engine] = {}
