# Publicar una versión

Esta guía es para quien mantiene el proyecto. Publicar una versión pone código en PyPI, que es
público y casi irreversible (una versión borrada no se puede volver a subir con ese número): revisa
cada paso antes de crear la etiqueta.

## Una sola vez: configurar PyPI

La publicación usa *trusted publishing* (OIDC): GitHub Actions demuestra a PyPI quién es y no hay
ningún token guardado en el repositorio.

1. En PyPI, crea el proyecto `osineitor` con un *pending publisher* (Cuenta → Publishing).
2. Rellena: propietario `jmstudio14`, repositorio `OSINEITOR`, flujo `release.yml`, entorno `pypi`.
3. En GitHub, crea el entorno `pypi` (Settings → Environments). Conviene exigir aprobación manual
   para que nada se publique sin una confirmación.

## Cada versión

1. Sube la versión en `pyproject.toml` y en `src/osineitor/__init__.py` (`__version__`).
2. Mueve lo de «Sin publicar» del [CHANGELOG](https://github.com/jmstudio14/OSINEITOR/blob/main/CHANGELOG.md) a la nueva versión.
3. Comprueba en local lo mismo que hace la CI: `ruff check .`, `ruff format --check .`,
   `python -m pytest -q`.
4. Fusiona en `main` y crea la etiqueta: `git tag v1.0.0 && git push origin v1.0.0`.
5. El flujo [`release.yml`](https://github.com/jmstudio14/OSINEITOR/blob/main/.github/workflows/release.yml) comprueba que la etiqueta coincide con
   la versión, ejecuta los tests, construye el wheel y el sdist, los revisa con `twine check` y, tras
   la aprobación del entorno `pypi`, los publica.

## Instalador de Windows

El job `windows` de `release.yml` (`windows-latest`, Python 3.13) corre tras `build`; el de PyPI no
lo necesita, así que si falla PyPI se publica igual. Pasos: `build.ps1` (PyInstaller y ZIP
portable), `smoke.py` sobre `dist/OSINEITOR`, Inno Setup (`ISCC /DMyAppVersion=…`, se instala con
`choco` si falta) y `checksums.py`, que escribe `SHA256SUMS.txt`. Sube los tres ficheros como
artefacto y, solo con una etiqueta, los adjunta a una Release de GitHub (`gh release create`). El
permiso `contents: write` está solo en ese job.

Para probarlo sin publicar: Actions → release → «Run workflow» (`workflow_dispatch`) construye y
sube los artefactos sin crear la Release ni tocar PyPI.

En local (PowerShell, con `pip install -e ".[gui,build]"`):

```powershell
.\packaging\windows\build.ps1 -Version 0.5.0
python packaging\windows\smoke.py dist\OSINEITOR
```

`ISCC` solo hace falta para el instalador (Inno Setup 6). Desde Git Bash, los argumentos `/D` se
reescriben como rutas: lánzalo desde PowerShell. No hay firma de código: el instalador y los `.exe`
salen sin firmar y Windows muestra SmartScreen. Firmarlos es una tarea del autor y exige un
certificado en HSM o firma en la nube (p. ej. Azure Trusted Signing o SignPath Foundation): desde
junio de 2023 los certificados nuevos no se exportan a PFX. Habría que firmar los `.exe` antes de
crear el ZIP y de `ISCC`, y después el instalador; `unins000.exe` queda aparte, y
`tests/test_packaging.py` hoy prohíbe secretos en el job `windows`. El instalador usa el icono por
defecto: no hay `.ico` en el repositorio.

## Firma

El paso de publicación genera *atestaciones* (PEP 740) firmadas con Sigstore: dejan constancia de
que cada fichero salió de este repositorio y de este flujo. En la página de cada fichero en PyPI
aparece como «Provenance». Para comprobarlas desde fuera se puede usar la herramienta
`pypi-attestations`.

## Qué se ha probado y qué no

- **Probado en local:** que el wheel y el sdist se construyen sin avisos, pasan `twine check`, incluyen
  los ficheros de datos (presets, reglas, firmas) y que el wheel instalado en un entorno limpio
  ejecuta `osineitor version`, lista todos los módulos y carga los presets.
- **Instalador de Windows, probado en local:** PyInstaller 6.22 (Python 3.14) construyó `dist/OSINEITOR` (134,8 MB; el ZIP, 66 MB) y `smoke.py` salió con 0: versión, 55 módulos (los que había entonces), presets, un scan sin red y la GUI viva a los 3 s.
- **Instalador de Windows, probado en local:** compilar el `.iss` con Inno Setup 6.7.3 (79,5 MB), instalar y desinstalar en silencio y `smoke.py` sobre lo instalado.
- **Instalador de Windows, no probado:** el asistente interactivo, el job `windows` en la CI (allí es Python 3.13), la creación de la Release, SmartScreen y los antivirus.
- **No probado:** el flujo `release.yml` completo, la publicación en PyPI y la comprobación de las
  atestaciones. Necesitan la cuenta de PyPI y los pasos de «Una sola vez». Hasta publicar una versión
  de prueba no hay evidencia de que funcionen; GitHub Actions rechaza el YAML si tiene un error de
  sintaxis, pero no el que sea de configuración de PyPI.
