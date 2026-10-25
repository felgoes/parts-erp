"""Explicit model-to-brand mapping for FENABRAVE public rankings.

The free ranking endpoint returns model names without brands. Unknown models are kept as
"Não mapeado" so rankings never hide or silently redistribute unmapped volume.
"""

MODEL_BRANDS = {
    "ARGO": "Fiat",
    "BIZ": "Honda",
    "CB 300F": "Honda",
    "CG 160": "Honda",
    "COMPASS": "Jeep",
    "CRETA": "Hyundai",
    "DOLPHIN": "BYD",
    "DOLPHIN MINI": "BYD",
    "FASTBACK": "Fiat",
    "HAVAL H6": "GWM",
    "HB20": "Hyundai",
    "HR-V": "Honda",
    "KWID": "Renault",
    "MOBI": "Fiat",
    "ONIX": "Chevrolet",
    "ONIX PLUS": "Chevrolet",
    "POLO": "Volkswagen",
    "PULSE": "Fiat",
    "T CROSS": "Volkswagen",
    "TERA": "Volkswagen",
    "TIGGO 7": "Chery",
    "TRACKER": "Chevrolet",
    "YARIS CROSS": "Toyota",
    "AMAROK": "Volkswagen",
    "DAKOTA": "Ram",
    "DUCATO": "Fiat",
    "EXPRESS": "Chevrolet",
    "FIORINO": "Fiat",
    "HILUX": "Toyota",
    "K2500": "Chevrolet",
    "MASTER": "Renault",
    "MAVERICK": "Ford",
    "MONTANA": "Chevrolet",
    "OROCH": "Renault",
    "POER": "GWM",
    "RAMPAGE": "Ram",
    "RANGER": "Ford",
    "S10": "Chevrolet",
    "SAVEIRO": "Volkswagen",
    "STRADA": "Fiat",
    "TORO": "Fiat",
    "TRITON": "Mitsubishi",
}


def brand_for_model(model: str | None) -> str:
    normalized = " ".join((model or "").upper().split())
    return MODEL_BRANDS.get(normalized, "Não mapeado")
