from __future__ import annotations

import re
import unicodedata

CARS = "cars"
MOTORCYCLES = "motorcycles"
CATEGORY_VERSION = 2

_MOTORCYCLE_BRANDS = {
    "AMAZON",
    "ASIA MOTOS",
    "ATALA",
    "BAJAJ",
    "BR MOTOS",
    "BRAMONT",
    "BRANDY",
    "BUELL",
    "CALOI",
    "CFMOTO",
    "CICLOMOTOR",
    "DAELIM",
    "DAFRA",
    "DAYANG",
    "DUCATI",
    "FLASH",
    "GAS GAS",
    "HAOBAO",
    "HARLEY DAVIDSON",
    "HARLEY-DAVIDSON",
    "H.DAVIDSON",
    "H-D",
    "HYOSUNG",
    "IABEL",
    "INDIAN",
    "IROS",
    "JCC",
    "JTA",
    "JTA-SUZUKI",
    "JTZ",
    "KAWASAKI",
    "KASINSKI",
    "KIN MOTORS",
    "KTM",
    "MAGNATA",
    "MONTESA",
    "MONARK",
    "MORINI",
    "MOTO",
    "MOTO TRAXX",
    "MOTOCAR",
    "MOTOCHEFE",
    "MOTORINO",
    "MOTTU",
    "MOTTUS",
    "MOTOVI",
    "MV AGUSTA",
    "SHINERAY",
    "SUPERMOTOS",
    "SUNDOWN",
    "SYM",
    "TIANJING",
    "TRAXX",
    "TRIUMPH",
    "TVS",
    "VMOTO",
    "VOGE",
    "WEMOTO",
    "YADEA",
    "YAMAHA",
    "ZONTES",
}

_HONDA_CAR_MODELS = (
    "ACCORD",
    "AIRWAVE",
    "BR-V",
    "BRV",
    "CITY",
    "CIVIC",
    "CLARITY",
    "CR-V",
    "CRIDER",
    "CRV",
    "CRX",
    "ELEMENT",
    "ELYSION",
    "FIT",
    "FR-V",
    "HR-V",
    "HRV",
    "INSIGHT",
    "JAZZ",
    "LIFE",
    "MOBILIO",
    "ODYSSEY",
    "PASSPORT",
    "PILOT",
    "PRELUDE",
    "RIDGELINE",
    "STREAM",
    "WR-V",
    "WRV",
    "ZR-V",
    "ZRV",
)

_SUZUKI_CAR_MODELS = (
    "AERIO",
    "ALTO",
    "BALENO",
    "CELERIO",
    "DZIRE",
    "ERTIGA",
    "ESTEEM",
    "FORENZA",
    "GRAND VITARA",
    "IGNIS",
    "JIMNY",
    "KIZASHI",
    "LIANA",
    "RENO",
    "S-CROSS",
    "SAMURAI",
    "SCROSS",
    "SIDEKICK",
    "SWIFT",
    "VITARA",
    "XL-7",
    "XL7",
)

_PIAGGIO_MOTORCYCLE_MODELS = (
    "APE",
    "BEVERLY",
    "BV",
    "CIAO",
    "FLY",
    "LIBERTY",
    "MEDLEY",
    "MP3",
    "NRG",
    "SI",
    "TYPHOON",
    "VESPA",
    "X8",
    "X9",
    "ZIP",
)

_BMW_MOTORCYCLE_SERIES = {"C", "CE", "F", "G", "HP", "K", "R", "S"}


def _key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return (
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .upper()
        .strip()
    )


_MOTORCYCLE_BRAND_KEYS = {_key(item) for item in _MOTORCYCLE_BRANDS}
_HONDA_CAR_MODEL_KEYS = tuple(_key(item) for item in _HONDA_CAR_MODELS)
_SUZUKI_CAR_MODEL_KEYS = tuple(_key(item) for item in _SUZUKI_CAR_MODELS)
_PIAGGIO_MOTORCYCLE_MODEL_KEYS = tuple(
    _key(item) for item in _PIAGGIO_MOTORCYCLE_MODELS
)


def _starts_with_any(value: str, prefixes: tuple[str, ...]) -> bool:
    return any(value.startswith(prefix) for prefix in prefixes)


def vehicle_category(brand: str, model: str) -> str:
    brand_key = _key(brand)
    model_key = _key(model)
    if brand_key in _MOTORCYCLE_BRAND_KEYS:
        return MOTORCYCLES
    if brand_key == "HONDA":
        return (
            CARS
            if _starts_with_any(model_key, _HONDA_CAR_MODEL_KEYS)
            else MOTORCYCLES
        )
    if brand_key == "SUZUKI":
        return (
            CARS
            if _starts_with_any(model_key, _SUZUKI_CAR_MODEL_KEYS)
            else MOTORCYCLES
        )
    if brand_key == "PIAGGIO":
        return (
            MOTORCYCLES
            if _starts_with_any(model_key, _PIAGGIO_MOTORCYCLE_MODEL_KEYS)
            else CARS
        )
    if brand_key == "BMW":
        match = re.match(r"^([A-Z]+)", model_key)
        series = match.group(1) if match else ""
        return MOTORCYCLES if series in _BMW_MOTORCYCLE_SERIES else CARS
    return CARS
