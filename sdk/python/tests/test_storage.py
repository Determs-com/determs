import json
import os
import tempfile
from pathlib import Path

from determs.record import build_record
from determs.storage import CallbackStorage, FileStorage, StdoutStorage, storage_from_env


def _record():
    return build_record(
        agent_id="a",
        model={"provider": "x", "name": "y"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        output={"content": "ok"},
    )


def test_file_storage_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        storage = FileStorage(tmp)
        record = _record()
        path = storage.put(record)
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["agent_id"] == "a"


def test_callback_storage_invokes_callback():
    captured: list[dict] = []
    storage = CallbackStorage(callback=captured.append)
    storage.put(_record())
    assert len(captured) == 1
    assert captured[0]["agent_id"] == "a"


def test_storage_from_env_defaults_to_file(monkeypatch):
    monkeypatch.delenv("DETERMS_STORAGE", raising=False)
    monkeypatch.delenv("DETERMS_DIR", raising=False)
    storage = storage_from_env()
    assert isinstance(storage, FileStorage)


def test_storage_from_env_stdout(monkeypatch):
    monkeypatch.setenv("DETERMS_STORAGE", "stdout")
    storage = storage_from_env()
    assert isinstance(storage, StdoutStorage)


def test_storage_from_env_file_directory(monkeypatch):
    monkeypatch.setenv("DETERMS_STORAGE", "file")
    monkeypatch.setenv("DETERMS_DIR", "/tmp/determs-test-dir")
    storage = storage_from_env()
    assert isinstance(storage, FileStorage)
    assert storage.directory == "/tmp/determs-test-dir"
