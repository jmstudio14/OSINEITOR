"""Aviso legal de la aplicación. Se muestra hasta que el usuario lo acepta."""

from __future__ import annotations

# Súbelo cuando el texto cambie de forma relevante: se volverá a pedir la aceptación.
LEGAL_VERSION = 1

LEGAL_TITLE = "Uso responsable"
LEGAL_TEXT = (
    "OSINEITOR consulta fuentes abiertas. Úsalo sobre objetivos propios o con autorización "
    "expresa. Investigar a personas físicas está sujeto al RGPD y a la legislación local: tú "
    "eres responsable del uso que hagas de la herramienta.\n\n"
    "Los módulos activos contactan directamente con el objetivo y pueden dejar rastro en sus "
    "registros; solo se ejecutan si lo confirmas expresamente."
)

ACTIVE_WARNING = (
    "Los módulos activos envían tráfico al objetivo, que podría registrarlo o detectarlo. "
    "Úsalos solo sobre sistemas propios o con autorización."
)
PRIVATE_WARNING = (
    "Permitir redes privadas desactiva la protección contra conexiones a tu propia red, a "
    "localhost y a los servicios de metadatos de una nube. Actívalo solo si investigas tu "
    "propia red."
)
