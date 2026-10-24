import re
from typing import Any


def _normalized_code(value: str | None) -> str:
    return "".join(character for character in (value or "").upper() if character.isalnum())


def _classify_offer(
    offer: dict[str, Any],
    oem: str | None,
    fitments: list[dict[str, Any]],
    catalog_listing_ids: set[str] | None = None,
) -> str:
    title = str(offer.get("title") or "").casefold()
    code = _normalized_code(oem)
    title_code = _normalized_code(title)
    if code and len(code) >= 4 and code in title_code:
        return "oem_exact"
    if str(offer.get("id") or "") in (catalog_listing_ids or set()):
        return "catalog"
    for fitment in fitments:
        make = str(fitment.get("make") or "").casefold().strip()
        model = str(fitment.get("model") or "").casefold().strip()
        engine = str(fitment.get("engine") or "").casefold().strip()
        version = str(fitment.get("version") or "").casefold().strip()
        year_from = fitment.get("year_from")
        year_to = fitment.get("year_to")
        year_tokens = {int(value) for value in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", title)}
        try:
            year_start = int(year_from) if year_from else None
        except (TypeError, ValueError):
            year_start = None
        try:
            year_end = int(year_to) if year_to else None
        except (TypeError, ValueError):
            year_end = None
        years_match = (
            not year_start
            and not year_end
            or any(
                (year_start is None or year >= year_start)
                and (year_end is None or year <= year_end)
                for year in year_tokens
            )
        )
        if (
            make
            and model
            and make in title
            and model in title
            and years_match
            and (not engine or engine in title)
            and (not version or version in title)
        ):
            return "fitment_confirmed"
    return "unconfirmed"
