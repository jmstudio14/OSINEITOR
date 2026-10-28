# Uso responsable

OSINEITOR automatiza consultas a fuentes abiertas. Que un dato sea accesible no significa que
cualquier uso sea legal o ético. Este documento no es asesoramiento jurídico.

## Principios

1. **Autorización.** Investiga activos propios o aquellos para los que tengas permiso por escrito
   (contrato de pentest, programa de bug bounty con alcance definido).
2. **Finalidad legítima y proporcionalidad.** Recoge solo lo necesario para el objetivo concreto.
3. **Pasivo primero.** Los módulos activos (`--active`) contactan al objetivo y pueden quedar
   registrados o activar alertas. Úsalos solo dentro del alcance autorizado.
4. **Respeta los términos de cada servicio**, sus cuotas y sus límites de uso.

## Datos personales (RGPD y LOPDGDD)

Emails, usernames, perfiles y filtraciones de una persona identificable son datos personales,
aunque sean públicos. Si los tratas fuera del ámbito puramente personal o doméstico:

- Necesitas una base legal (art. 6 RGPD), normalmente el interés legítimo documentado.
- Debes minimizar los datos, limitar el tiempo de conservación y protegerlos.
- Los datos de filtraciones pueden incluir categorías especiales: trátalos con más cuidado aún.

Fuera de la UE aplica la legislación local (p. ej. la Ley 25.326 en Argentina).

## Usos no aceptables

- Acoso, doxing, vigilancia o seguimiento de personas.
- Elaborar perfiles de personas sin base legal, o con fines discriminatorios o de manipulación.
- Usar credenciales filtradas para acceder a cuentas.
- Investigar a menores.
- Cualquier uso contra los otros participantes del proyecto.

## Buenas prácticas

- Documenta el alcance y la autorización antes de empezar.
- Guarda los resultados cifrados o en un equipo controlado; la base de datos y los informes se
  guardan sin cifrar (ver [SECURITY.md](../SECURITY.md)).
- Borra los scans cuando termine la investigación.
- Verifica los hallazgos antes de actuar sobre ellos: las fuentes se equivocan y la búsqueda de
  usernames produce falsos positivos.

## Si eres el objetivo

Para reducir tu exposición: [JustDeleteMe](https://justdeleteme.xyz/es) para borrar cuentas,
[Have I Been Pwned](https://haveibeenpwned.com) para revisar filtraciones y el derecho de
supresión (art. 17 RGPD) ante quien publique tus datos.
