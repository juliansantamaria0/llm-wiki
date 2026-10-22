"""Registro por contenido y extracción explícita, sin síntesis automática."""

from pathlib import Path

from llm_wiki.storage import Project, WikiError, digest, json_bytes, now, read_bytes

SUPPORTED = {".md", ".txt", ".pdf"}
MAX_EXTRACT_CHARS = 200_000


def add_source(project: Project, source_path: Path) -> dict:
    if source_path.is_symlink() or source_path.is_junction():
        raise WikiError("No se importan enlaces de sistema.")
    if source_path.suffix.lower() not in SUPPORTED:
        raise WikiError("Formato no admitido. Usa .md, .txt o .pdf.")
    content = read_bytes(source_path)
    if not content:
        raise WikiError("La fuente está vacía.")
    sha = digest(content)
    source_id = f"src-{sha}"
    state = project.state()
    if source_id in state["sources"]:
        source = state["sources"][source_id]
        verify_source(project, source)
        return {"id": source_id, "duplicate": True, **source}
    relative = f"raw/sources/{source_id}{source_path.suffix.lower()}"
    if project.path(relative).exists():
        raise WikiError(
            "Ya hay un archivo sin registrar con ese destino; revísalo antes de importar."
        )
    source = {
        "id": source_id,
        "name": source_path.name,
        "path": relative,
        "sha256": sha,
        "added_at": now(),
        "ingested_sha256": None,
    }
    state["sources"][source_id] = source
    log = project.path("log.md").read_text(encoding="utf-8")
    project.commit(
        {
            relative: content,
            ".llm-wiki/state.json": json_bytes(state),
            "log.md": (log + f"\n## [{now()}] add | {source_id}\n").encode(),
        }
    )
    return {**source, "duplicate": False}


def verify_source(project: Project, source: dict) -> bytes:
    try:
        content = read_bytes(project.path(source["path"]))
    except FileNotFoundError as exc:
        raise WikiError(f"Falta la fuente: {source['id']}") from exc
    if digest(content) != source["sha256"]:
        raise WikiError(
            f"Fuente modificada: {source['id']}. Restaura la copia original o importa una nueva versión desde otro archivo."
        )
    return content


def extract(project: Project, source: dict) -> str:
    content = verify_source(project, source)
    suffix = Path(source["path"]).suffix
    if suffix in (".md", ".txt"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise WikiError(
                "Convierte el documento de texto a UTF-8 antes de procesarlo."
            ) from exc
    else:
        try:
            from pypdf import PdfReader
            from pypdf.errors import PyPdfError
        except ImportError as exc:
            raise WikiError(
                "Para PDF instala el extra 'pdf': pipx inject llm-wiki-local 'pypdf>=6.1,<7'."
            ) from exc
        try:
            reader = PdfReader(project.path(source["path"]))
            if reader.is_encrypted:
                raise WikiError(
                    "PDF cifrado: exporta una copia accesible antes de importarlo."
                )
            if len(reader.pages) > 500:
                raise WikiError(
                    "PDF de más de 500 páginas: divídelo antes de procesarlo."
                )
            parts = []
            total = 0
            for number, page in enumerate(reader.pages, 1):
                text_page = page.extract_text() or ""
                total += len(text_page)
                if total > MAX_EXTRACT_CHARS:
                    raise WikiError(
                        "Texto demasiado largo; divide el documento. No se truncó el contenido."
                    )
                if not text_page.strip():
                    raise WikiError(
                        f"La página {number} no tiene texto extraíble. Revisa si necesita OCR antes de continuar."
                    )
                parts.append(f"[Página {number}]\n{text_page}")
            text = "\n\n".join(parts)
        except (PyPdfError, ValueError) as exc:
            raise WikiError("No se pudo leer el PDF. Revisa su integridad.") from exc
    if not text.strip():
        raise WikiError(
            "No hay texto extraíble. Los documentos escaneados necesitan OCR externo."
        )
    if len(text) > MAX_EXTRACT_CHARS:
        raise WikiError(
            "Texto demasiado largo; divide el documento. No se truncó el contenido."
        )
    return text
