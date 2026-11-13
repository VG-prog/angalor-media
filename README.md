# Media de Angalor

Este repositorio reúne los recursos públicos del ecosistema. No contiene bases de
cuentas, claves, adjuntos privados ni ejecutables de los reinos.

- `web/` conserva las rutas de imágenes, iconos, fuentes, audio y vídeo de la web
  y del foro. Por ejemplo, `web/application/images/armory/` contiene sus mapas.
- `modelviewer/` contiene los modelos, texturas, animaciones y el índice de su
  publicación. `modelviewer/current` identifica la publicación disponible.
- `publication.json` registra los archivos y sus SHA-256. Se publica después de
  los archivos; su presencia identifica una exportación completa.

Los archivos se preparan y suben desde el servidor. No se utiliza GitHub Actions
ni Git LFS. `tools/publish.py` actualiza esta copia desde los directorios públicos
instalados, comprueba sus archivos y divide la subida en lotes. Si se interrumpe,
volver a ejecutar el mismo comando continúa la subida de los archivos conservados.
Cada ejecución verifica el catálogo completo, pero sólo añade al índice de Git
los archivos nuevos o modificados desde la última publicación completa. Un lote
ya subido antes de una interrupción se reconcilia al reanudar; el manifiesto final
sigue publicándose después de todos sus recursos.

La entrega web debe fijar un commit completo de este repositorio. El mismo árbol
puede servirse desde GitHub, un servidor de media propio o el servidor principal.
Los recursos publicados no necesitan que se arranque un emulador.

Las imágenes y recursos de World of Warcraft conservan la titularidad de sus
autores. Este repositorio no cambia su licencia ni su atribución.

## Origen de entrega

El servidor utiliza `/srv/angalor/media`. La web y el foro conservan sus URL públicas;
Nginx redirige sus imágenes, fuentes y vídeos al commit completo de este repositorio.
El visor redirige sus modelos y texturas por SHA-256. El código JavaScript/CSS se
sirve desde la web con su tipo MIME correcto. Cloudflare puede conservar copias
válidas de archivos ya descargados.

Para seleccionar GitHub, el comando de infraestructura es:

```sh
sudo python3 /srv/angalor/local-ecosystem/tools/configure-public-media.py --gateway /home/debian/cluster-workspace/launcher-bolivia --apply --receipt /var/lib/angalor/media-github-AAAA-MM-DD
```

Usa un directorio de recibo nuevo en cada cambio. Añadir `--local` sirve los archivos
desde este mismo repositorio. Para otro servidor, copia allí `web/`
y `modelviewer/` del mismo commit completo y añade `--origin https://media.tu-dominio/ruta`.
Ese servidor debe permitir lectura CORS de los recursos públicos. Sin `--apply`,
el comando comprueba la publicación y muestra el cambio sin activarlo.

Para actualizar los recursos, ejecuta primero `tools/publish.py` con `--web-root
/srv/angalor/fusioncms/htdocs --model-root /srv/angalor/local-ecosystem/runtime/data/modelviewer
--repo /srv/angalor/media --git-user debian` como administrador del servidor.
Después selecciona la publicación completa con el comando anterior. Una exportación
incompleta se rechaza; no se activa el último lote a medio subir.

Para una generación preparada con `modelviewer_archive.py publish --stage`, añade
`--model-release ID` al publicador. El `current` del archivo fuente permanece intacto.
Durante la subida, los lectores deben seguir usando ese archivo y la publicación
anterior, no el `current` del checkout que se está modificando. Después de terminar
y verificar la subida, `configure-public-media.py` selecciona el checkout completo
y su nuevo origen. Los commits sólo incluyen las rutas de cada lote y conservan
cualquier trabajo ajeno que ya esté en el índice de Git.

Las vistas previas usan el ID de esa generación en su ruta. Antes de activarla,
incluir también las imágenes de ficha, galería y miniaturas bajo ese ID. Una
adición exclusiva de audio permite reutilizar sus bytes sólo después de comprobar
que todos los modelos, texturas y recursos del visor anteriores son idénticos y
que las imágenes coinciden con la publicación previa. Si cambian esos recursos,
hay que regenerar las imágenes afectadas.

Si Git falla, `.publish/git-failure.log` conserva su diagnóstico con permisos
privados. Comprobar el commit remoto antes de reintentar un envío interrumpido;
un timeout no confirma si GitHub recibió la operación.
