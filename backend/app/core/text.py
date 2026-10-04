import re


_LOWERCASE_PARTICLES = {"a", "as", "da", "das", "de", "do", "dos", "e", "em"}


def normalize_customer_name(value: str) -> str:
    """Return a readable display name without destroying accents or hyphens."""
    words = re.split(r"\s+", value.strip())
    normalized: list[str] = []
    for index, word in enumerate(words):
        if not word:
            continue
        lower = word.lower()
        if index > 0 and lower in _LOWERCASE_PARTICLES:
            normalized.append(lower)
        else:
            normalized.append(lower[:1].upper() + lower[1:])
    return " ".join(normalized)
