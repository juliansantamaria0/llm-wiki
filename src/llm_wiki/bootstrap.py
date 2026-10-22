"""Inicialización conservadora de una carpeta de conocimiento."""

import os
import tempfile
from importlib.resources import files
from pathlib import Path

from llm_wiki.storage import WikiError, json_bytes, now


def template(name: str) -> str:
    return files("llm_wiki").joinpath("templates", name).read_text(encoding="utf-8")


def initialize(root: Path, name: str, profile: str) -> Path:
    root = root.absolute()
    if root.is_symlink() or root.is_junction():
        raise WikiError("Inicializa una carpeta normal, sin enlaces de sistema.")
    if (
        not name.strip()
        or not profile.strip()
        or len(name) > 200
        or len(profile) > 8000
    ):
        raise WikiError(
            "Indica nombre (1–200 caracteres) y perfil (1–8000 caracteres)."
        )
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise WikiError(
            "La inicialización necesita una carpeta vacía; no sobrescribe archivos."
        )
    generated = {
        ".llm-wiki/config.json": json_bytes(
            {
                "schema": 1,
                "name": name.strip(),
                "profile": profile.strip(),
                "created_at": now(),
            }
        ),
        ".llm-wiki/state.json": json_bytes({"schema": 1, "sources": {}, "pages": {}}),
        "AGENTS.md": template("AGENTS.md").encode(),
        "CLAUDE.md": b"# LLM Wiki\n\nLee AGENTS.md y .claude/skills/llm-wiki/SKILL.md para operar esta wiki.\n",
        ".agents/skills/llm-wiki/SKILL.md": template("SKILL.md").encode(),
        ".claude/skills/llm-wiki/SKILL.md": template("SKILL.md").encode(),
        "wiki/index.md": b"# Wiki\n\nTodavia no hay fuentes procesadas.\n",
        "log.md": b"# Historial de la wiki\n",
        "START_HERE.md": template("START_HERE.md").encode(),
        ".gitignore": b"# Datos personales: excluidos por defecto\nraw/\nwiki/\n.llm-wiki/\nlog.md\nAGENTS.md\nCLAUDE.md\n.agents/\n.claude/\n.env*\n*.key\n*.pem\n",
    }
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".llm-wiki-init-", dir=root.parent
    ) as temporary:
        staged = Path(temporary) / "project"
        for directory in (
            "raw/sources",
            "wiki/sources",
            "wiki/concepts",
            "wiki/entities",
            "wiki/syntheses",
            ".llm-wiki/drafts",
        ):
            (staged / directory).mkdir(parents=True, exist_ok=True)
        for relative, content in generated.items():
            path = staged / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content)
        if root.exists():
            root.rmdir()  # Fails safely if files appeared since the initial check.
        os.replace(staged, root)
    return root
