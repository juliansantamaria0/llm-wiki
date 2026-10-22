import base64
import json

import pytest

from llm_wiki import storage
from llm_wiki.storage import JOURNAL, WikiError, json_bytes


def test_failed_write_rolls_back_all_changes(project, monkeypatch):
    old = project.path("log.md").read_bytes()
    original_write = storage.atomic_write
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path.name == "b.md" and not failed:
            failed = True
            raise OSError("Fallo de disco simulado")
        original_write(path, data)

    monkeypatch.setattr(storage, "atomic_write", fail_once)
    with project.operation(), pytest.raises(OSError):
        project.commit(
            {
                "log.md": b"changed",
                "wiki/concepts/a.md": b"first",
                "wiki/concepts/b.md": b"second",
            }
        )
    assert project.path("log.md").read_bytes() == old
    assert not project.path("wiki/concepts/a.md").exists()
    assert not project.path(JOURNAL).exists()


def test_interruption_leaves_recoverable_journal(project, monkeypatch):
    class SimulatedCrash(BaseException):
        pass

    old = project.path("log.md").read_bytes()
    original_write = storage.atomic_write

    def crash(path, data):
        if path.name == "a.md":
            raise SimulatedCrash()
        original_write(path, data)

    monkeypatch.setattr(storage, "atomic_write", crash)
    with project.operation(), pytest.raises(SimulatedCrash):
        project.commit({"log.md": b"new log", "wiki/concepts/a.md": b"new page"})
    assert project.path(JOURNAL).exists()
    with pytest.raises(WikiError, match="interrumpida"), project.operation():
        pass
    monkeypatch.setattr(storage, "atomic_write", original_write)
    with project.operation(recovery=True):
        assert project.recover()
    assert project.path("log.md").read_bytes() == old
    assert not project.path("wiki/concepts/a.md").exists()


def test_recovery_preserves_edits_made_after_crash(project):
    project.path("log.md").write_bytes(b"human edit")
    journal = {
        "schema": 1,
        "entries": [
            {
                "path": "log.md",
                "before": base64.b64encode(b"before").decode(),
                "after": base64.b64encode(b"after").decode(),
            }
        ],
    }
    project.path(JOURNAL).write_bytes(json_bytes(journal))
    with (
        project.operation(recovery=True),
        pytest.raises(WikiError, match="cambió fuera"),
    ):
        project.recover()
    assert project.path("log.md").read_bytes() == b"human edit"
    assert project.path(JOURNAL).exists()


def test_concurrent_operation_fails_instead_of_interleaving(project):
    with project.operation():
        with pytest.raises(WikiError, match="ocupada"), project.operation():
            pass


def test_tampered_journal_cannot_write_outside(project, tmp_path):
    outside = tmp_path / "keep.txt"
    outside.write_bytes(b"KEEP")
    project.path(JOURNAL).write_text(
        json.dumps(
            {
                "schema": 1,
                "entries": [{"path": "../keep.txt", "before": None, "after": ""}],
            }
        ),
        encoding="utf-8",
    )
    with (
        project.operation(recovery=True),
        pytest.raises(WikiError, match="destino inválido"),
    ):
        project.recover()
    assert outside.read_bytes() == b"KEEP"
