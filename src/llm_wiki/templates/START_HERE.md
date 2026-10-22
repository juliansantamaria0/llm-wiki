# Tu wiki está preparada

Abre esta carpeta en el chat de un asistente que pueda leer archivos y ejecutar
comandos locales. Pídele:

> Lee AGENTS.md y la skill LLM Wiki. Procesa los documentos que dejé en raw/.

Después puedes escribir:

> ¿Qué compromisos aparecen en los documentos? Cita las fuentes.

> Revisa la wiki: busca contradicciones, páginas aisladas y temas incompletos.

El asistente ya tiene tu perfil en `.llm-wiki/config.json`; actualízalo cuando
cambien tus necesidades. Los archivos Markdown se pueden abrir en cualquier editor.

La instalación global aporta la CLI; esta carpeta aporta las instrucciones y la
memoria de tu proyecto. Si el cliente no carga la skill automáticamente, pídele
leer `.agents/skills/llm-wiki/SKILL.md`. Puede hacer falta reabrir la carpeta o sesión.
La detección automática debe comprobarse en cada cliente.

`llm-wiki status` muestra pendientes. Registrar un documento no equivale a haberlo
sintetizado. Las operaciones `ingest` y `query` preparan datos para el asistente;
la respuesta y las síntesis las produce el modelo del chat.

Esta carpeta excluye datos de Git por defecto. Conserva copias de seguridad de toda
la carpeta (incluida `.llm-wiki/`), además de cualquier historial que decidas guardar.
