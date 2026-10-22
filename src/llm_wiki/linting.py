"""Lint estructural; las contradicciones requieren revisión semántica."""

import posixpath
import re
from urllib.parse import unquote, urlsplit

from llm_wiki.storage import Project, WikiError, digest, read_bytes

INLINE_LINK = re.compile(r"\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")


def link_targets(content: str) -> list[str]:
    # Supported subset: inline Markdown links. Reference links/HTML/Obsidian are not parsed.
    content = re.sub(r"```.*?```|~~~.*?~~~", "", content, flags=re.S)
    content = re.sub(r"`[^`\n]*`", "", content)
    return [match.group(1).strip("<>") for match in INLINE_LINK.finditer(content)]


def local_target(relative: str, target: str) -> str | None:
    parts = urlsplit(target)
    if parts.scheme in ("http", "https", "mailto") or (
        not parts.path and parts.fragment
    ):
        return None
    if parts.scheme or parts.netloc or target.startswith("/") or "\\" in target:
        raise WikiError("Destino de enlace no permitido.")
    decoded = unquote(parts.path)
    return posixpath.normpath(posixpath.join(posixpath.dirname(relative), decoded))


def broken_links(
    project: Project, relative: str, content: str, known_pages: set[str]
) -> list[str]:
    broken = []
    for target in link_targets(content):
        try:
            normalized = local_target(relative, target)
            if normalized is None:
                continue
            path = project.path(normalized)
            if normalized not in known_pages and not path.is_file():
                broken.append(target)
        except (WikiError, ValueError):
            broken.append(target)
    return broken


def lint(project: Project) -> dict:
    from llm_wiki.workflows import PROVENANCE, index_text, pages_on_disk

    state = project.state()
    issues = []

    def issue(code: str, path: str, detail: str, severity: str = "error"):
        issues.append(
            {"code": code, "path": path, "detail": detail, "severity": severity}
        )

    for source_id, source in state["sources"].items():
        try:
            data = read_bytes(project.path(source["path"]))
            if digest(data) != source["sha256"]:
                issue(
                    "source_changed", source["path"], "El original registrado cambió."
                )
        except FileNotFoundError:
            issue("source_missing", source["path"], source_id)
        if source["ingested_sha256"] is None:
            issue(
                "source_pending",
                source["path"],
                "Registrada, todavía sin síntesis aplicada.",
                "warning",
            )
    pages = pages_on_disk(project)
    for relative, metadata in state["pages"].items():
        if relative not in pages:
            issue("page_missing", relative, "Falta una página registrada.")
            continue
        if digest(pages[relative].encode()) != metadata["sha256"]:
            issue(
                "page_edited",
                relative,
                "Edición fuera de apply; revisa y vuelve a aplicar para registrar procedencia.",
                "warning",
            )
        for source_id, sha in metadata["sources"].items():
            source = state["sources"].get(source_id)
            if not source or source["sha256"] != sha:
                issue(
                    "stale_provenance",
                    relative,
                    f"Fuente desconocida o versión diferente: {source_id}",
                )
        if PROVENANCE not in pages[relative]:
            issue(
                "provenance_missing", relative, "No hay bloque de fuentes verificables."
            )
    incoming = {path: set() for path in pages}
    for relative, content in pages.items():
        if relative != "wiki/index.md" and relative not in state["pages"]:
            issue(
                "page_untracked",
                relative,
                "Página manual sin procedencia registrada.",
                "warning",
            )
        for target in broken_links(project, relative, content, set(pages)):
            issue("broken_link", relative, target)
        if relative != "wiki/index.md":
            for target in link_targets(content):
                try:
                    normalized = local_target(relative, target)
                    if normalized in incoming and normalized != relative:
                        incoming[normalized].add(relative)
                except (WikiError, ValueError):
                    continue
    for relative, origins in incoming.items():
        if relative != "wiki/index.md" and not origins:
            issue(
                "isolated_page",
                relative,
                "Sin enlaces entrantes desde otras páginas de conocimiento; el índice no cuenta.",
                "warning",
            )
    if state["pages"] and pages.get("wiki/index.md") != index_text(pages):
        issue(
            "index_outdated",
            "wiki/index.md",
            "El índice no coincide con las páginas actuales.",
            "warning",
        )
    return {
        "issues": issues,
        "errors": sum(item["severity"] == "error" for item in issues),
        "warnings": sum(item["severity"] == "warning" for item in issues),
        "semantic_review": "Pendiente de revisión por el asistente: contradicciones, afirmaciones sin respaldo y vacíos de conocimiento. El lint no los certifica.",
        "link_support": "Enlaces Markdown inline; no verifica anclas, enlaces externos, referencias Markdown, HTML ni wikilinks de Obsidian.",
    }
