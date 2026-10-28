# Política de seguridad

## Versiones con soporte

OSINEITOR está en fase inicial (0.x). Solo se corrigen fallos en la última versión de `main`.

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

## Qué no lo es

- Que una fuente de terceros devuelva datos incorrectos o deje de funcionar: abre un issue normal.
- Falsos positivos en la búsqueda de usernames: es una limitación conocida (ver README).

## Datos sensibles que gestiona la herramienta

- **API keys:** `~/.config/osineitor/config.toml`, creado con permisos `0600`, o variables de
  entorno `OSINEITOR_<NOMBRE>_KEY`. `osineitor config show` las muestra enmascaradas.
- **Resultados:** `~/.local/share/osineitor/osineitor.db` (SQLite, sin cifrar) y los informes en
  `reports/`. Pueden contener datos personales: protégelos y bórralos cuando ya no los necesites.
