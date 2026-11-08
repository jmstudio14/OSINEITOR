# Política de seguridad

## Versiones con soporte

OSINEITOR está en desarrollo (0.x, aún sin la 1.0). Solo se corrigen fallos en la última versión de `main`.

## Cómo informar de una vulnerabilidad

**No abras un issue público.** Usa el aviso privado de GitHub:
pestaña *Security* del repositorio → *Report a vulnerability*.

Incluye:

- Descripción del fallo y su impacto.
- Pasos para reproducirlo (versión, comando, entrada).
- Si lo tienes, una propuesta de corrección.

Se intentará responder en un plazo de 7 días y publicar la corrección antes de divulgar detalles.

## Qué se considera vulnerabilidad

- Fugas de API keys (en logs, informes, base de datos o mensajes de error).
- Ejecución de código o lectura/escritura de ficheros a partir de datos devueltos por una fuente
  externa o de la entrada del usuario.
- Inyección (HTML/JS) en los informes exportados.
- Módulos marcados como pasivos que en realidad contactan al objetivo.
- Datos de un scan enviados a un proveedor de IA remoto sin `consent_remote: true` en `ai.yml`, o
  una clave de API, una URL de webhook o una contraseña SMTP que aparezcan en un error, en un log
  o en un informe.
- Una forma de saltarse la guardia de red (conexiones a IPs privadas, loopback o metadatos cloud,
  también por redirecciones) o de alterar la ruta de una URL con una entrada manipulada.

**Límite conocido:** entre la comprobación de la guardia y la conexión el DNS podría cambiar
(*DNS rebinding*). Fijar la IP resuelta en la conexión está pendiente. Lo que sí hace la guardia:
bloquea un nombre que no resuelve (no deja pasar la petición) y las IPv4 escondidas en IPv6
(NAT64, IPv4-compatible), y el cliente ignora los proxies del entorno.

**Plugins:** los módulos de terceros se cargan por *entry point* y se ejecutan con tus permisos,
sin aislamiento. Instala solo plugins que hayas revisado.

## Qué no lo es

- Que una fuente de terceros devuelva datos incorrectos o deje de funcionar: abre un issue normal.
- Falsos positivos en la búsqueda de usernames: es una limitación conocida (ver README).

## Datos sensibles que gestiona la herramienta

- **API keys:** `config.toml` en el directorio de configuración (`%APPDATA%\osineitor` en Windows,
  `~/.config/osineitor` en Linux). En Linux y macOS se crea con permisos `0600`; en Windows se
  restringe a tu usuario con `icacls`. No se cifra. También se pueden pasar con variables de entorno
  `OSINEITOR_<NOMBRE>_KEY`. `osineitor config show` las muestra enmascaradas.
- **Vigilancia e IA:** `watch.yml` y `ai.yml` van en el mismo directorio de configuración. Las URLs
  de webhook, las contraseñas SMTP y las claves de los proveedores de IA se leen de variables de
  entorno (`url_env`, `password_env`, `api_key_env`) y no deberían ir en el fichero. Con un
  proveedor de IA remoto, los hechos del scan (que pueden incluir emails o usernames) salen de tu
  máquina solo si lo has permitido en `ai.yml`.
- **Publicación:** el flujo de PyPI usa publicación de confianza (OIDC) y no guarda ningún token en
  el repositorio; la imagen Docker corre sin privilegios. Ambos están descritos pero **sin
  ejecutar todavía** ([PUBLICACION.md](docs/PUBLICACION.md)).
- **Resultados:** `osineitor.db` en el directorio de datos (SQLite, sin cifrar) y los informes en
  `reports/`. `osineitor.db` y `cache.db` se crean con permisos `0600` en POSIX. Pueden contener
  datos personales: protégelos y bórralos cuando ya no los necesites.
- **Respuestas de las fuentes:** el cliente HTTP corta cualquier respuesta a los 64 MiB ya
  descomprimidos (`ResponseTooLarge`, sin reintento), para que una fuente hostil no agote la memoria.
