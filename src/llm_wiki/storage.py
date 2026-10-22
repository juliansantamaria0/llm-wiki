"""Rutas confinadas, exclusión entre procesos y escritura recuperable."""

import base64
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 20 * 1024 * 1024
STATE = ".llm-wiki/state.json"
JOURNAL = ".llm-wiki/journal.json"
RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)
}


class WikiError(Exception):
    """Error operativo que puede presentarse al usuario sin traceback."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise WikiError(f"Clave JSON duplicada: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise WikiError(f"Constante JSON no válida: {value}")

    try:
        if path.stat().st_size > max_bytes:
            raise WikiError(f"JSON demasiado grande: {path.name}")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WikiError(f"JSON inválido: {path.name}") from exc
    if not isinstance(value, dict):
        raise WikiError(f"Se esperaba un objeto JSON: {path.name}")
    return value


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise WikiError("La ruta debe ser relativa y usar '/'.")
    parts = relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(
        part in ("", ".", "..")
        or re.search(r'[<>:"|?*\x00-\x1f]', part)
        or part.endswith((".", " "))
        or part.split(".")[0].lower() in RESERVED
        for part in parts
    ):
        raise WikiError(f"Ruta no permitida: {relative!r}")
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink() or path.is_junction():
            raise WikiError(f"No se permiten enlaces de sistema: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise WikiError("La ruta sale del proyecto.")
    return path


def read_bytes(path: Path) -> bytes:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise WikiError(f"Archivo mayor de 20 MiB: {path.name}")
    return path.read_bytes()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".llm-wiki-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def allowed_target(relative: str) -> bool:
    return (
        relative in (STATE, "wiki/index.md", "log.md")
        or bool(
            re.fullmatch(
                r"wiki/(sources|concepts|entities|syntheses)/[a-z0-9][a-z0-9._-]*\.md",
                relative,
            )
        )
        or bool(re.fullmatch(r"raw/sources/src-[a-f0-9]{64}\.(md|txt|pdf)", relative))
    )


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not safe_path(self.root, ".llm-wiki/config.json").is_file():
            raise WikiError("Esta carpeta no es una wiki. Ejecuta 'llm-wiki init'.")

    def path(self, relative: str) -> Path:
        return safe_path(self.root, relative)

    @contextmanager
    def operation(self, *, recovery: bool = False):
        lock = self.path(".llm-wiki/lock.sqlite3")
        try:
            connection = sqlite3.connect(lock, timeout=0)
            try:
                connection.execute("BEGIN IMMEDIATE")
                if self.path(JOURNAL).exists() and not recovery:
                    raise WikiError(
                        "Hay una escritura interrumpida. Ejecuta 'llm-wiki recover'."
                    )
                yield self
            finally:
                connection.rollback()
                connection.close()
        except sqlite3.OperationalError as exc:
            raise WikiError(
                "La wiki está ocupada o no se puede bloquear. Reintenta al terminar la otra operación."
            ) from exc

    def state(self) -> dict:
        value = read_json(self.path(STATE))
        if (
            value.get("schema") != 1
            or not isinstance(value.get("sources"), dict)
            or not isinstance(value.get("pages"), dict)
        ):
            raise WikiError("El registro de la wiki tiene un esquema inválido.")
        for source_id, source in value["sources"].items():
            if not re.fullmatch(r"src-[a-f0-9]{64}", source_id) or not isinstance(
                source, dict
            ):
                raise WikiError("Registro de fuentes inválido.")
            expected = f"raw/sources/{source_id}."
            if (
                not isinstance(source.get("path"), str)
                or not source["path"].startswith(expected)
                or not allowed_target(source["path"])
            ):
                raise WikiError("Ruta de fuente inválida en el registro.")
            if source.get("sha256") != source_id[4:]:
                raise WikiError("Huella de fuente inválida en el registro.")
            if (
                source.get("id") != source_id
                or not isinstance(source.get("name"), str)
                or not isinstance(source.get("added_at"), str)
                or "ingested_sha256" not in source
                or source["ingested_sha256"] not in (None, source["sha256"])
            ):
                raise WikiError("Metadatos de fuente inválidos en el registro.")
        for page, metadata in value["pages"].items():
            if (
                not page.startswith("wiki/")
                or not allowed_target(page)
                or page == "wiki/index.md"
                or not isinstance(metadata, dict)
                or not isinstance(metadata.get("sources"), dict)
            ):
                raise WikiError("Registro de páginas inválido.")
            if (
                not isinstance(metadata.get("sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", metadata["sha256"])
                or not isinstance(metadata.get("updated_at"), str)
                or not metadata["sources"]
                or any(
                    not re.fullmatch(r"src-[a-f0-9]{64}", key)
                    or not isinstance(sha, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", sha)
                    for key, sha in metadata["sources"].items()
                )
            ):
                raise WikiError("Metadatos de página inválidos en el registro.")
        return value

    def commit(self, writes: dict[str, bytes]) -> None:
        """Rollback de errores ordinarios; diario durable para interrupciones."""
        entries = []
        total_bytes = 0
        for relative, after in writes.items():
            if not allowed_target(relative):
                raise WikiError(f"Destino de transacción inválido: {relative}")
            target = self.path(relative)
            before = read_bytes(target) if target.exists() else None
            if len(after) > MAX_FILE_BYTES:
                raise WikiError(f"El archivo resultante supera 20 MiB: {relative}")
            total_bytes += len(after) + (len(before) if before is not None else 0)
            if total_bytes > 64 * 1024 * 1024:
                raise WikiError(
                    "La transacción supera 64 MiB de versiones; divide la actualización."
                )
            entries.append(
                {
                    "path": relative,
                    "before": base64.b64encode(before).decode()
                    if before is not None
                    else None,
                    "after": base64.b64encode(after).decode(),
                }
            )
        atomic_write(self.path(JOURNAL), json_bytes({"schema": 1, "entries": entries}))
        try:
            for entry in entries:
                atomic_write(self.path(entry["path"]), base64.b64decode(entry["after"]))
        except OSError:
            self.recover()
            raise
        self.path(JOURNAL).unlink()

    def recover(self) -> bool:
        journal_path = self.path(JOURNAL)
        if not journal_path.exists():
            return False
        journal = read_json(journal_path, max_bytes=128 * 1024 * 1024)
        if journal.get("schema") != 1 or not isinstance(journal.get("entries"), list):
            raise WikiError("Diario inválido; conserva una copia y revisa el proyecto.")
        entries = []
        seen = set()
        for entry in journal["entries"]:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("path"), str)
                or not allowed_target(entry["path"])
            ):
                raise WikiError("El diario contiene un destino inválido.")
            if entry["path"] in seen:
                raise WikiError("El diario contiene destinos duplicados.")
            seen.add(entry["path"])
            try:
                before = (
                    base64.b64decode(entry["before"], validate=True)
                    if entry.get("before") is not None
                    else None
                )
                after = base64.b64decode(entry["after"], validate=True)
            except (ValueError, TypeError, KeyError) as exc:
                raise WikiError("Contenido inválido en el diario.") from exc
            path = self.path(entry["path"])
            current = read_bytes(path) if path.exists() else None
            if current not in (before, after):
                raise WikiError(
                    f"Recuperación detenida: {entry['path']} cambió fuera de la transacción. Conserva el diario y revisa esa edición."
                )
            entries.append((path, before))
        for path, before in reversed(entries):
            if before is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, before)
        journal_path.unlink()
        return True
