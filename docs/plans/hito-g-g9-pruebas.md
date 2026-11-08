# Plan G9 · Pruebas manuales en Windows (Hito G)

> **Para quien lo ejecute:** esta tarea la ejecuta el autor en un Windows real; la CI no puede.
> Lo que sí hace un agente es preparar la lista, comprobar que es coherente y registrar los
> resultados que el autor le dicte. Los pasos usan casillas `- [ ]`.

**Objetivo:** una lista de comprobación ejecutable, con resultado esperado en cada punto, que dé
por terminado el Hito G, y un registro de lo que se probó, cuándo y con qué.

**Arquitectura:** sin código nuevo. Una sección «Aplicación de escritorio» en
[`docs/PRUEBAS_WINDOWS.md`](../PRUEBAS_WINDOWS.md) (que ya tiene la estructura «Cómo anotar los
resultados» y «Registro de resultados») y la actualización de las notas «Qué no está verificado».

**Spec:** [`ROADMAP.md`](../../ROADMAP.md) (Hito G, fila G9), la lista manual de
[`docs/GUI.md`](../GUI.md) y sus 7 criterios de aceptación.

## Restricciones globales

- Una casilla se marca solo con evidencia: captura, salida literal o nota con fecha. Lo que no se
  haya ejecutado se queda sin marcar y en «Qué no está verificado».
- Se prueba el **instalador y el ZIP construidos por la CI** (G8), no `pip install -e`.
- Ejecutar con una cuenta de usuario normal (sin administrador) y con la carpeta de usuario con
  espacios o acentos si es posible.
- El resultado fallido se anota igual que el correcto, con la salida literal.
- Cierra el hito solo si pasan todos los puntos marcados como «bloqueantes».

## Foco de revisión

- DPI al 150 % y 200 %: texto cortado en los diálogos nuevos (Nuevo scan con el selector de
  módulos, Ajustes, Salud).
- Tema del sistema cambiado en caliente (claro ↔ oscuro) con la ventana abierta.
- Cerrar la ventana con un scan en marcha: `tasklist | findstr osineitor` no muestra procesos
  huérfanos (ni `osineitor.exe` ni `python.exe`).
- Primer arranque con `%APPDATA%\osineitor-gui` borrado: aviso legal; rechazarlo cierra sin dejar
  procesos.
- Sin conexión a Internet: un scan pasivo muestra los módulos con error o `quota`, no una ventana
  congelada.
- Antivirus/SmartScreen: anotar qué muestra y si bloquea.

## Estructura de ficheros

| Fichero | Cambio |
|---|---|
| `docs/PRUEBAS_WINDOWS.md` | sección «Aplicación de escritorio», con tabla de resultados |
| `docs/GUI.md` | quitar de «Qué no está verificado» lo comprobado; borrar la lista manual duplicada y enlazar a la sección nueva |
| `ROADMAP.md` | G9 ✅ solo cuando haya resultados reales; «Estado» con fecha |
| `CHANGELOG.md` | una línea |

---

### Tarea 1: redactar la lista (agente)

- [ ] **Paso 1:** léela entera y comprueba que cada punto trae **acción** y **resultado esperado**.
  Puntos mínimos, agrupados:
  - *Instalación:* instalar el `setup.exe` sin administrador; aviso de SmartScreen (anotar texto);
    acceso directo del menú Inicio; instalar encima de la misma versión (sin duplicados);
    `osineitor.exe version --json` desde una terminal nueva (con y sin la opción de PATH).
    **Bloqueante.**
  - *Primer arranque:* aviso legal visible; «Salir» cierra sin ventana; «Acepto» no vuelve a
    preguntar al reabrir. **Bloqueante.**
  - *Scan:* `example.com` pasivo; actividad por módulo en vivo; entidades en la tabla; detalle de
    entidad; cancelar a mitad (pestaña marcada como cancelada, aparece en el historial);
    dominio `.es` → `rdap` «omitido». **Bloqueante.**
  - *Historial y exportación:* abrir un scan guardado; exportar JSON, Markdown y HTML; abrir el HTML
    en el navegador. **Bloqueante.**
  - *Seguridad (G7):* marcar «activos» → confirmación; rechazar → no se lanza; aceptar → se lanza
    y la CLI recibió `--active`; igual con redes privadas. **Bloqueante.**
  - *Ajustes (G6):* guardar una API key y borrarla; `osineitor config show` coincide; la key no
    aparece en ninguna ventana. **Bloqueante.**
  - *Salud (G5):* «Comprobar» rellena la tabla; cerrar el diálogo a mitad no cuelga la ventana.
  - *Aspecto:* modo oscuro; DPI 150 % y 200 %; la ventana recuerda tamaño y tema.
  - *Cierre:* cerrar con un scan en marcha pide confirmación y no deja procesos (`tasklist`).
  - *Desinstalación:* desinstalar con la aplicación cerrada y con ella abierta; no queda la carpeta
    de instalación; `%APPDATA%` se conserva y así se dice en el desinstalador.
  - *ZIP portable:* descomprimir en una ruta con espacios; ejecutar `osineitor-gui.exe` sin instalar.
  - *SHA-256:* `Get-FileHash` coincide con `SHA256SUMS.txt`.
- [ ] **Paso 2:** los enlaces y comandos de la sección pasan `python -m pytest tests/test_docs.py -q`
  (el test de documentación valida enlaces relativos y que los comandos citados existan).
- [ ] **Paso 3:** commit `Añade la lista de pruebas manuales de la aplicación de escritorio (G9)`.

### Tarea 2: ejecutar (autor)

- [ ] **Paso 1:** descarga los artefactos de la CI del commit exacto que se va a publicar; anota
  versión, fecha, versión de Windows (`winver`), escala de pantalla y antivirus.
- [ ] **Paso 2:** recorre la lista. Cada punto: `✅`, `❌` o `⏭️` (no aplicable) más la evidencia.
- [ ] **Paso 3:** los `❌` se abren como incidencias con la salida literal; si es un fallo de los
  planes G5–G8, se arregla en el plan correspondiente y se repite el punto.

### Tarea 3: cerrar el hito (agente, con los resultados del autor)

- [ ] **Paso 1:** copia los resultados a «Registro de resultados» de `docs/PRUEBAS_WINDOWS.md`
  con fecha y versión; no resumas una salida literal.
- [ ] **Paso 2:** actualiza «Qué no está verificado» de `docs/GUI.md`: solo se quita lo que tiene
  evidencia en el registro.
- [ ] **Paso 3:** `ROADMAP.md`: G9 ✅ si pasan todos los bloqueantes; si no, 🟡 con la lista de lo
  pendiente. Actualiza la fecha de «Estado» y el criterio del hito.
- [ ] **Paso 4:** `ruff check . && ruff format --check . && python -m pytest -q` → verde.
- [ ] **Paso 5:** commit `Registra las pruebas manuales de la aplicación de escritorio (G9)`.

## Qué no cubre

- macOS y Linux (la GUI es solo Windows). Pruebas de carga o de accesibilidad con lector de
  pantalla (si se quiere, es un entregable aparte; existe la skill `accessibility-review`).
