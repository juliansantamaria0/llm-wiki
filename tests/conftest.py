import pytest

from llm_wiki.bootstrap import initialize
from llm_wiki.storage import Project


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "wiki personal"
    initialize(
        root,
        "Contratos de prueba",
        "Organizo compromisos y fechas de contratos ficticios.",
    )
    return Project(root)
