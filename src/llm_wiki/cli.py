"""Interfaz global; JSON estable para poder operarla desde un chat."""

import argparse
import json
import sys
from pathlib import Path

from llm_wiki import __version__
from llm_wiki.bootstrap import initialize
from llm_wiki.linting import lint
from llm_wiki.sources import add_source
from llm_wiki.storage import Project, WikiError, json_bytes, read_json
from llm_wiki.workflows import apply_plan, ingest_packet, query_packet


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="llm-wiki",
        description="Tu wiki local, mantenida desde el chat de tu asistente.",
    )
    root.add_argument("--version", action="version", version=f"LLM Wiki {__version__}")
    root.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Carpeta de la wiki; antes del subcomando.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser(
        "init", help="Inicializa una carpeta vacía y personaliza el contexto."
    )
    init.add_argument("directory", type=Path, nargs="?")
    init.add_argument("--name")
    init.add_argument("--profile")
    init.add_argument(
        "--no-input",
        action="store_true",
        help="No hace preguntas; requiere --name y --profile.",
    )
    commands.add_parser(
        "status", help="Muestra fuentes pendientes, páginas y estado de recuperación."
    )
    add = commands.add_parser(
        "add", help="Registra una copia verificable de una fuente."
    )
    add.add_argument("file", type=Path)
    commands.add_parser(
        "scan", help="Registra documentos de raw/; omite las copias ya gestionadas."
    )
    ingest = commands.add_parser(
        "ingest", help="Prepara texto y contexto para que el asistente sintetice."
    )
    ingest.add_argument("source_id")
    ingest.add_argument("--output", type=Path)
    apply = commands.add_parser(
        "apply", help="Valida y aplica un plan JSON creado por el asistente."
    )
    apply.add_argument("plan", type=Path)
    apply.add_argument("--dry-run", action="store_true")
    query = commands.add_parser(
        "query", help="Prepara contexto de la wiki para responder en el chat."
    )
    query.add_argument("question")
    query.add_argument("--max-chars", type=int, default=60_000)
    query.add_argument("--output", type=Path)
    lint_command = commands.add_parser(
        "lint", help="Comprueba enlaces, originales, procedencia e índice."
    )
    lint_command.add_argument(
        "--strict",
        action="store_true",
        help="También devuelve error cuando hay advertencias.",
    )
    commands.add_parser(
        "recover",
        help="Revierte una escritura interrumpida sin pisar ediciones posteriores.",
    )
    return root


def dispatch(args: argparse.Namespace) -> tuple[dict, int]:
    if args.command == "init":
        name, profile = args.name, args.profile
        if not name or not profile:
            if args.no_input or not sys.stdin.isatty():
                raise WikiError(
                    "Desde el chat usa --name y --profile. El asistente debe preguntarte primero lo que falte."
                )
            name = name or input("¿Cómo se llamará tu wiki? ").strip()
            profile = (
                profile
                or input("¿Quién eres y para qué usarás estos documentos? ").strip()
            )
        root = initialize(args.directory or args.project, name, profile)
        return {
            "project": str(root),
            "next": "Abre esta carpeta en tu asistente y lee START_HERE.md. Deposita documentos en raw/ y pide que los procese.",
        }, 0
    project = Project(args.project)
    with project.operation(recovery=args.command in ("recover", "status")):
        if args.command == "recover":
            return {"recovered": project.recover()}, 0
        if args.command == "status":
            state = project.state()
            return {
                "sources": list(state["sources"].values()),
                "pending": [
                    key
                    for key, source in state["sources"].items()
                    if source["ingested_sha256"] is None
                ],
                "pages": len(state["pages"]),
                "recovery_required": project.path(".llm-wiki/journal.json").exists(),
            }, 0
        if args.command == "add":
            return add_source(project, args.file), 0
        if args.command == "scan":
            results, errors = [], []
            raw = project.path("raw")
            for path in sorted(raw.rglob("*")):
                relative = path.relative_to(project.root).as_posix()
                if relative.startswith("raw/sources/"):
                    continue
                try:
                    project.path(relative)
                    if path.is_dir():
                        continue
                    results.append(add_source(project, path))
                except (WikiError, OSError, UnicodeError) as exc:
                    errors.append({"path": relative, "error": str(exc)})
            return {"sources": results, "errors": errors}, 1 if errors else 0
        if args.command == "ingest":
            return ingest_packet(project, args.source_id), 0
        if args.command == "apply":
            return apply_plan(project, read_json(args.plan), dry_run=args.dry_run), 0
        if args.command == "query":
            return query_packet(project, args.question, args.max_chars), 0
        if args.command == "lint":
            result = lint(project)
            return result, 1 if result["errors"] or (
                args.strict and result["warnings"]
            ) else 0
    raise WikiError("Operación desconocida.")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result, exit_code = dispatch(args)
        if getattr(args, "output", None):
            # Exclusive creation prevents accidentally replacing a source, plan or page.
            output = args.output
            with output.open("xb") as stream:
                stream.write(json_bytes(result))
            print(json.dumps({"output": str(output)}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except (WikiError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperación cancelada.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
