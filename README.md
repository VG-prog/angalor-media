# Media de Angalor

Este repositorio reúne los recursos públicos del ecosistema. No contiene bases de
cuentas, claves, adjuntos privados ni ejecutables de los reinos.

- `web/` conserva las rutas de imágenes, iconos, fuentes, audio y vídeo de la web
  y del foro. Por ejemplo, `web/application/images/armory/` contiene sus mapas.
- `modelviewer/` contiene los modelos, texturas, animaciones y el índice de su
  publicación. `modelviewer/current` identifica la publicación disponible.
- `publication.json` registra los archivos y sus SHA-256. Se publica después de
  los archivos; su presencia identifica una exportación completa.

Los archivos se preparan y suben desde el dedicado. No se utiliza GitHub Actions
ni Git LFS. `tools/publish.py` actualiza esta copia desde los directorios públicos
instalados, comprueba sus archivos y divide la subida en lotes. Si se interrumpe,
volver a ejecutar el mismo comando continúa la subida de los archivos conservados.

La entrega web debe fijar un commit completo de este repositorio. El mismo árbol
puede servirse desde GitHub, un servidor de media propio o el servidor principal.
Los recursos publicados no necesitan que se arranque un emulador.

Las imágenes y recursos de World of Warcraft conservan la titularidad de sus
autores. Este repositorio no cambia su licencia ni su atribución.
