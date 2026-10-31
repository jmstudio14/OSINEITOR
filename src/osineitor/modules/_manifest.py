"""Lista explícita de los ficheros de módulos.

`pkgutil.walk_packages` no es fiable dentro de un ejecutable empaquetado (PyInstaller), así que
allí se importan estos nombres. `tests/test_registry.py` exige que la lista coincida con lo que
hay en disco: al añadir un módulo, añádelo también aquí.
"""

MODULES = (
    "osineitor.modules.domain.cert_details",
    "osineitor.modules.domain.crtsh",
    "osineitor.modules.domain.dns",
    "osineitor.modules.domain.http_fingerprint",
    "osineitor.modules.domain.mail_security",
    "osineitor.modules.domain.rdap",
    "osineitor.modules.domain.saas_footprint",
    "osineitor.modules.domain.wayback",
    "osineitor.modules.domain.whois",
    "osineitor.modules.email.gravatar",
    "osineitor.modules.email.hibp",
    "osineitor.modules.email.hunter",
    "osineitor.modules.email.validate",
    "osineitor.modules.ip.abuseipdb",
    "osineitor.modules.ip.cve_enrich",
    "osineitor.modules.ip.geo",
    "osineitor.modules.ip.greynoise",
    "osineitor.modules.ip.internetdb",
    "osineitor.modules.ip.shodan",
    "osineitor.modules.username.sites",
)
