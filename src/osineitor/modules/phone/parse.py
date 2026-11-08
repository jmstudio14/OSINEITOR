"""País, región, tipo de línea y formatos de un teléfono (en local, con `phonenumbers`)."""

from __future__ import annotations

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder, timezone

from osineitor.models import Entity, EntityType
from osineitor.modules.base import Module

LINE_TYPES = {
    PhoneNumberType.FIXED_LINE: "fijo",
    PhoneNumberType.MOBILE: "móvil",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fijo o móvil",
    PhoneNumberType.TOLL_FREE: "gratuito",
    PhoneNumberType.PREMIUM_RATE: "tarificación especial",
    PhoneNumberType.SHARED_COST: "coste compartido",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal",
    PhoneNumberType.PAGER: "buscapersonas",
    PhoneNumberType.UAN: "acceso universal",
    PhoneNumberType.VOICEMAIL: "buzón de voz",
}
LANGUAGE = "es"


class PhoneParse(Module):
    name = "phone_parse"
    description = "País, región, tipo de línea, operador de origen y formatos de un teléfono"
    consumes = frozenset({EntityType.PHONE})
    produces = frozenset({EntityType.RECORD})
    canary = "+34612345678"

    async def run(self, entity: Entity) -> list[Entity]:
        number = phonenumbers.parse(entity.value, None)
        line = phonenumbers.number_type(number)
        return [
            self.emit(
                entity,
                EntityType.RECORD,
                f"phone:{entity.value}",
                valid=phonenumbers.is_valid_number(number),
                possible=phonenumbers.is_possible_number(number),
                country_code=number.country_code,
                region=phonenumbers.region_code_for_number(number),
                country=geocoder.country_name_for_number(number, LANGUAGE) or None,
                area=geocoder.description_for_number(number, LANGUAGE) or None,
                line_type=LINE_TYPES.get(line, "desconocido"),
                # El operador es el de la asignación original: la portabilidad no se refleja.
                original_carrier=carrier.name_for_number(number, LANGUAGE) or None,
                time_zones=list(timezone.time_zones_for_number(number)),
                international=phonenumbers.format_number(number, PhoneNumberFormat.INTERNATIONAL),
                national=phonenumbers.format_number(number, PhoneNumberFormat.NATIONAL),
                rfc3966=phonenumbers.format_number(number, PhoneNumberFormat.RFC3966),
            )
        ]
