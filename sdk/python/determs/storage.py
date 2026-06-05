"""Storage backends for action records.

Each backend exposes a single method ``put(record: ActionRecord) -> str``
that persists the record and returns an identifier (path, URL, etc.).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from determs.record import ActionRecord


class Storage(Protocol):
    """A storage backend for action records."""

    def put(self, record: ActionRecord) -> str:
        ...


@dataclass
class FileStorage:
    """Write each record as ``<directory>/<action_id>.json``."""

    directory: str

    def put(self, record: ActionRecord) -> str:
        path = Path(self.directory)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{record.action_id}.json"
        target.write_text(record.to_json() + "\n", encoding="utf-8")
        return str(target)


@dataclass
class StdoutStorage:
    """Write each record as a JSON line to stdout. Useful for piping."""

    pretty: bool = False

    def put(self, record: ActionRecord) -> str:
        if self.pretty:
            sys.stdout.write(record.to_json() + "\n")
        else:
            sys.stdout.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        sys.stdout.flush()
        return f"stdout:{record.action_id}"


@dataclass
class CallbackStorage:
    """Hand the record dict to a user-supplied callback.

    Useful for testing or for custom integrations (queues, custom HTTP
    sinks, etc.).
    """

    callback: Callable[[dict], None]

    def put(self, record: ActionRecord) -> str:
        self.callback(record.to_dict())
        return f"callback:{record.action_id}"


def storage_from_env(default_dir: Optional[str] = None) -> Storage:
    """Pick a storage backend from environment variables.

    - ``DETERMS_STORAGE=stdout`` → :class:`StdoutStorage`
    - ``DETERMS_STORAGE=file`` (default) → :class:`FileStorage` at
      ``DETERMS_DIR`` (or ``./determs_records`` or ``default_dir``)
    """
    kind = os.environ.get("DETERMS_STORAGE", "file").strip().lower()
    if kind == "stdout":
        return StdoutStorage()
    directory = os.environ.get("DETERMS_DIR") or default_dir or "./determs_records"
    return FileStorage(directory=directory)
