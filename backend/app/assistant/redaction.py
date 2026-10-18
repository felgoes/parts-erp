"""Filtra credenciais e dados desnecessários antes de mostrar ou enviar conteúdo à IA."""

import re

PATTERNS = (
    re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/-]{8,}=*"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret)\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(password|senha)\b\s*[:=]\s*\S+"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
)


def redact(value: str, limit: int = 1200) -> str:
    text = value or ""
    replacements = (
        "[chave removida]",
        r"\1 [credencial removida]",
        r"\1=[credencial removida]",
        r"\1=[credencial removida]",
        "[e-mail removido]",
        "[documento removido]",
    )
    for pattern, replacement in zip(PATTERNS, replacements, strict=True):
        text = pattern.sub(replacement, text)
    return text[:limit]


def clean_mapping(value: dict, limit: int = 1200) -> dict:
    return {str(key)[:60]: redact(str(item), limit) for key, item in value.items()}
