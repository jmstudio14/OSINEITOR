# Línea base de falsos positivos de `username_sites`

Entregable F0.5 del [roadmap](https://github.com/jmstudio14/OSINEITOR/blob/main/ROADMAP.md). Medido el 2026-11-05 con `python scripts/fp_baseline.py -n 5` desde Windows 11 (Python 3.14.10), red doméstica en España, versión 0.5.0 y las firmas de Sherlock que trae el paquete.
- **Usernames inexistentes probados:** 5
- **Comprobaciones evaluables:** 2286
- **Falsos positivos:** 6
- **Tasa:** 0.26%

## Por username

| Username | Falsos positivos |
|---|---|
| `ibdjflal3y6zpl` | 1 |
| `wg2xq494a8s8v2` | 3 |
| `g678yty90b792m` | 1 |
| `xbpgo6k079jno8` | 0 |
| `ydwkfrd1qwctf9` | 1 |

## Sitios con falsos positivos

| Sitio | Veces |
|---|---|
| Chatujme.cz | 3 |
| Envato Forum | 1 |
| Tweakers | 1 |
| Needrom | 1 |

## Cómo leerlo

- **Es la tasa residual, no la anterior a la fase 1.** El script ejecuta el módulo tal como está, con su verificación por username de control: un positivo que el sitio también da a un username inexistente se descarta. Nunca se midió la tasa sin esa verificación, así que el criterio de la fase 1 («baja al menos un 50 % respecto a la línea base») **no se puede comprobar** con este número.
- **Denominador:** las comprobaciones evaluables son las firmas cuyo `regexCheck` admite el username (unas 457 de las 462 por username). No descuenta los sitios que no respondieron (la ejecución registró varios `http.error`): un sitio caído cuenta como «no encontrado».
- **Muestra pequeña:** 5 usernames y 6 positivos. Chatujme.cz acierta falsamente con 3 de los 5, pero no con todos, así que no es un error sistemático de la firma.
- Las firmas de `sites.json` no se editan a mano (se actualizan descargándolas de nuevo): los cuatro sitios listados son candidatos a revisar o a excluir en una actualización.

## Repetir la medición

Hace unas 2.300 peticiones a sitios de terceros: ejecútalo solo desde tu red.

```powershell
python scripts/fp_baseline.py -n 5 --output reports/fp_baseline.md
```
