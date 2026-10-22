# Diseño y contrato de la primera versión

## Alcance

CLI instalable globalmente, con asistente de chat como motor semántico. Runtime base
sin dependencias de terceros; argparse, pathlib, hashlib, sqlite3 y json pertenecen
a Python. El extra PDF añade pypdf. No es un servidor, un chatbot web ni un servicio
de inferencia. No hay configuración de modelos ni claves API en esta versión.

El patrón conceptual LLM Wiki aportado por el usuario es una referencia de diseño.
No se copiaron implementaciones externas ni instrucciones de documentos fuente como
autorización para ejecutar acciones. La implementación separa originales, wiki e
instrucciones y trata las afirmaciones sobre memoria y mantenimiento como objetivos,
no garantías de exactitud.

## Contrato de planes

`ingest ID` emite un objeto con la fuente, texto extraído, páginas existentes,
huellas de página y ejemplo de plan. El asistente produce JSON UTF-8 válido:

```json
{
  "kind": "ingest",
  "summary": "Resume el contrato y documenta su fecha de entrega.",
  "sources": {"src_HAY_QUE_SUSTITUIR": "SHA256_REAL"},
  "pages": [
    {
      "path": "wiki/concepts/entregas.md",
      "expected_sha256": null,
      "sources": ["src_HAY_QUE_SUSTITUIR"],
      "content": "# Entregas\n\nContenido respaldado por el documento."
    }
  ]
}
```

El ejemplo anterior explica el esquema; los identificadores son marcadores y se
rechazan al ejecutar. Usa los valores reales emitidos por `ingest`. Un identificador
real tiene la forma `src-` seguida de 64 dígitos hexadecimales.

- `kind=ingest`: toda fuente pendiente declarada necesita su resumen
  `wiki/sources/ID.md` dentro del plan. Solo al aplicar se marca como procesada.
- `kind=update`: permite síntesis de consultas y mantenimiento utilizando fuentes
  ya procesadas. No marca fuentes nuevas como ingeridas.
- Cada página debe declarar fuentes que existan en el registro y cuyas huellas
  coincidan. Una página actualizada conserva la procedencia anterior.
- `expected_sha256=null` indica una página nueva; para una existente, usa la huella
  completa de su contenido actual. Un conflicto obliga a releer y reconciliar.
- El contenido enviado no incluye el bloque reservado de procedencia. La CLI añade
  enlaces relativos a las fuentes y su SHA-256 automáticamente.
- Solo se escriben páginas Markdown en las cuatro carpetas documentadas, con
  nombres ASCII en minúscula. No hay borrado de páginas ni de fuentes en v0.1.
- Los enlaces inline se validan sobre el conjunto final de páginas; es posible crear
  páginas que se enlacen mutuamente dentro del mismo plan.

Para preparar un plan, usa `ingest` como referencia del esquema y las huellas; no
ejecutes el plan de ejemplo como si constituyera una síntesis real.

## Integridad y fallos

Una conexión SQLite con BEGIN IMMEDIATE excluye operaciones simultáneas cooperantes.
No guarda conocimiento: únicamente aporta un bloqueo liberado por el sistema tras
terminar el proceso. Los clientes que editan archivos directamente no participan del
bloqueo; las huellas detectan cambios anteriores a la aplicación. Evita editar la
wiki manualmente durante una escritura.

Las escrituras se preparan con un diario durable que conserva contenido anterior y
nuevo. Cada archivo se reemplaza individualmente con os.replace. Ante un error
ordinario se intenta rollback; tras una interrupción se exige `recover`. Recuperar
verifica que ningún archivo afectado contenga una edición posterior antes de
restaurar. No es una transacción atómica del sistema de archivos ante cualquier
fallo de hardware. El diario y las copias de seguridad complementan esa limitación.

`log.md` es acumulativo durante la operación normal. Una recuperación revierte la
entrada de una transacción incompleta. El CLI no permite borrar el historial como
parte de un plan; alguien con acceso al sistema de archivos sí puede modificarlo.

## Límites explícitos

- Archivos fuente hasta 20 MiB; .md/.txt UTF-8 y PDFs con texto como extra opcional.
- PDFs: máximo 500 páginas; una página sin texto detiene la extracción para evitar
  omitir silenciosamente contenido. No hay OCR integrado ni soporte para PDF cifrado.
- Texto extraído: hasta 200.000 caracteres; se rechaza el exceso, no se trunca.
- Contexto de ingesta: wiki de hasta 300.000 caracteres, además de fuente/metadatos.
- Consulta: selección léxica, presupuesto configurable de 1.000–300.000 caracteres
  de páginas. No representa tokens ni el tamaño total del JSON. Declara omisiones.
- Planes de hasta 4 MiB, 100 páginas y 200.000 caracteres de contenido por página.
- Lint: enlaces Markdown inline, existencia de archivo, huellas y procedencia.
  No verifica anclas, URLs externas, wikilinks, referencias Markdown ni HTML.
- Una página aislada no recibe enlaces de otras páginas de conocimiento; el índice
  no cuenta. Puede ser normal en una wiki pequeña, por eso es una advertencia.
- Las contradicciones se documentan mediante el LLM. El lint no valida semántica,
  vigencia legal, exactitud de fechas ni que cada afirmación tenga una cita correcta.
- La resistencia de un modelo a prompt injection requiere evaluación independiente.
  El CLI no ejecuta instrucciones del contenido ni proporciona herramientas al texto.
- No se ha verificado descubrimiento automático en clientes de chat reales.

Para wikis mayores, la próxima extensión debería seleccionar contexto por páginas y
referencias sin perder fuentes, añadir una cola de ingestas y evaluar la calidad
semántica con documentos de prueba. Las búsquedas sobre fuentes y RAG pueden
complementar la wiki; son compatibles con este patrón.
