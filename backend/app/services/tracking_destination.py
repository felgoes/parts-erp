from collections.abc import Mapping
from typing import Any
from unicodedata import normalize

from app.models import MarketplaceOrder

DESTINATION_METADATA_KEY = "_erp_destination_address"
LOCALITY_METADATA_KEY = "_erp_destination_locality"
STATE_NAMES = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM",
    "bahia": "BA", "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES",
    "goias": "GO", "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC",
    "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}
STATE_CODES = frozenset(STATE_NAMES.values())


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _place_name(value: object) -> str | None:
    if isinstance(value, Mapping):
        return _text(value.get("name")) or _text(value.get("id"))
    return _text(value)


def _first_address(shipment: Mapping[str, Any]) -> Mapping[str, Any] | str | None:
    for key in ("receiver_address", "shipping_address", "destination"):
        candidate = shipment.get(key)
        if isinstance(candidate, Mapping):
            for nested_key in ("address", "shipping_address"):
                nested = candidate.get(nested_key)
                if isinstance(nested, Mapping):
                    return nested
            return candidate
        if _text(candidate):
            return str(candidate)
    return None


def format_shipping_destination(shipment: Mapping[str, Any] | None) -> str | None:
    """Format only the delivery address fields exposed by Mercado Envios."""
    if not isinstance(shipment, Mapping):
        return None
    address = _first_address(shipment)
    if not address:
        return None
    if isinstance(address, str):
        return _text(address)

    line = _text(address.get("address_line"))
    street = _text(address.get("street_name")) or _text(address.get("street"))
    number = _text(address.get("street_number")) or _text(address.get("number"))
    if not line:
        line = street
        if line and number and number.casefold() not in line.casefold():
            line = f"{line}, {number}"
    complement = _text(address.get("complement"))
    if line and complement and complement.casefold() not in line.casefold():
        line = f"{line} - {complement}"

    neighborhood = _place_name(address.get("neighborhood"))
    city = _place_name(address.get("city"))
    state = _place_name(address.get("state"))
    locality = " - ".join(part for part in (city, state) if part)
    postal_code = _text(address.get("zip_code")) or _text(address.get("postal_code"))

    parts = [line, neighborhood, locality, f"CEP {postal_code}" if postal_code else None]
    return " · ".join(dict.fromkeys(part for part in parts if part))[:500] or None


def tracking_destination_address(order: MarketplaceOrder) -> str | None:
    payload = order.payload if isinstance(order.payload, dict) else {}
    return _text(payload.get(DESTINATION_METADATA_KEY))


def shipping_destination_locality(shipment: Mapping[str, Any] | None) -> str | None:
    if not isinstance(shipment, Mapping):
        return None
    return shipping_address_locality(_first_address(shipment))


def shipping_address_locality(address: object) -> str | None:
    if not isinstance(address, Mapping):
        return None
    city_value = address.get("city")
    city = _text(city_value.get("name")) if isinstance(city_value, Mapping) else _text(city_value)
    state_value = address.get("state")
    candidates = (state_value.get("id"), state_value.get("name")) if isinstance(state_value, Mapping) else (state_value,)
    for value in candidates:
        state = _text(value) or ""
        code = state.upper().removeprefix("BR-")
        name = normalize("NFKD", state).encode("ascii", "ignore").decode().casefold()
        uf = code if code in STATE_CODES else STATE_NAMES.get(name)
        if city and uf:
            return f"{city}, {uf}"
    return None


def tracking_destination_locality(order: MarketplaceOrder) -> str | None:
    payload = order.payload if isinstance(order.payload, dict) else {}
    return _text(payload.get(LOCALITY_METADATA_KEY))


def persist_tracking_destination(
    order: MarketplaceOrder, shipment: Mapping[str, Any] | None
) -> str | None:
    address = format_shipping_destination(shipment)
    locality = shipping_destination_locality(shipment)
    updates = {}
    if address and address != tracking_destination_address(order):
        updates[DESTINATION_METADATA_KEY] = address
    if locality and locality != tracking_destination_locality(order):
        updates[LOCALITY_METADATA_KEY] = locality
    if updates:
        order.payload = {**(order.payload or {}), **updates}
    return address
