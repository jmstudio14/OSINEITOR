## Qué cambia

<!-- Resumen del cambio y motivo. Enlaza el issue si existe (Closes #N). -->

## Tipo

- [ ] Nueva fuente / módulo
- [ ] Corrección de error
- [ ] Mejora del núcleo, CLI o informes
- [ ] Documentación

## Cómo se ha probado

- [ ] `ruff check .` y `ruff format --check .`
- [ ] `python -m pytest -q`
- [ ] Prueba real contra el servicio (indica el comando y el resultado, sin datos personales)

## Checklist para módulos nuevos

- [ ] Tests sin red: caso con datos, caso vacío y un error
- [ ] `passive = False` si contacta al objetivo
- [ ] `requires_key` y nombre de la key documentados en el README
- [ ] Entrada en `docs/MODULES.md`, tabla del README y `CHANGELOG.md`
- [ ] Cumple [docs/USO_RESPONSABLE.md](../docs/USO_RESPONSABLE.md)
