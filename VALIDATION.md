# Validación de la primera entrega

Fecha: 22 de octubre de 2026. Versión: 0.1.0.

- Windows, Python 3.12.14: **42 pruebas pasadas, 1 omitida**.
- La prueba omitida necesita crear symlinks; este entorno de Windows no concede ese
  permiso. Se mantienen pruebas de rutas relativas, nombres reservados, enlaces
  Markdown peligrosos y diarios manipulados. El caso de symlink queda pendiente
  para un entorno que lo permita, como el job Linux de CI.
- Ruff: lint y formato correctos.
- Wheel y sdist construidos sin conexión, con las plantillas dentro del paquete.
- Instalación de la rueda con pipx (backend uv) en un entorno temporal separado:
  ejecutable `llm-wiki` verificado sin cargar el código desde el árbol de fuentes.
- Recorrido desde ese ejecutable: versión, init, scan, status, ingest, apply en modo
  validación, apply, query y lint; dos páginas interconectadas, cero problemas de lint,
  originales conservados. La síntesis de prueba se escribió explícitamente a partir
  de un contrato ficticio; no se invocó un modelo para generarla.
- Las dos copias de la skill generada pasaron el validador quick_validate de
  skill-creator. Esa comprobación valida formato, no comportamiento del modelo.
- PDF opcional: extracción real con pypdf 6.10.0, páginas sin texto, cifrado,
  archivo inválido y dependencia ausente.
- Pruebas del ciclo de ingesta, consulta con fuentes, conservación de originales,
  duplicados, conflictos de edición, planes inválidos, presupuesto de contexto,
  mantenimiento con dos fuentes y preservación de procedencia.
- Pruebas de bloqueo, rollback, recuperación tras interrupción y preservación de
  ediciones realizadas después de una interrupción.

Las pruebas usaron documentos ficticios y no ejecutaron un proveedor de modelos.
El caso de contenido malicioso verifica que el CLI no lo ejecuta; no certifica la
resistencia de un LLM a inyección de prompts. La calidad de las síntesis, el manejo
de contradicciones y la detección automática de skills requieren evaluación en el
asistente elegido.

Las comprobaciones anteriores corresponden a la entrega local. Los resultados de
los workflows remotos se consultan en [GitHub Actions](https://github.com/juliansantamaria0/llm-wiki/actions).
No se publicaron paquetes en PyPI.
