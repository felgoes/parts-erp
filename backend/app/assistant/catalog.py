"""Catálogo fechado de provedores, modelos e preços de referência.

O preço é uma estimativa para o orçamento do ERP, não a fatura do provedor. Modelos fora
deste catálogo ficam bloqueados porque sem preço confiável não há como medir consumo.
"""

from dataclasses import dataclass
from decimal import Decimal

PRICING_UPDATED_AT = "2026-10-18"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    input_per_million: Decimal
    output_per_million: Decimal


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    base_url: str
    docs_url: str
    models: tuple[ModelSpec, ...]

    def model(self, model_id: str) -> ModelSpec | None:
        return next((item for item in self.models if item.id == model_id), None)


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        docs_url="https://developers.openai.com/api/reference/overview",
        models=(
            ModelSpec("gpt-4.1-mini", "GPT-4.1 mini", Decimal("0.40"), Decimal("1.60")),
            ModelSpec("gpt-4.1", "GPT-4.1", Decimal("2.00"), Decimal("8.00")),
        ),
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        docs_url="https://api-docs.deepseek.com/quick_start/pricing/",
        models=(
            ModelSpec("deepseek-chat", "DeepSeek Chat", Decimal("0.27"), Decimal("1.10")),
            ModelSpec("deepseek-reasoner", "DeepSeek Reasoner", Decimal("0.55"), Decimal("2.19")),
        ),
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        docs_url="https://ai.google.dev/gemini-api/docs/partner-integration",
        models=(
            ModelSpec("gemini-2.5-flash", "Gemini 2.5 Flash", Decimal("0.30"), Decimal("2.50")),
            ModelSpec("gemini-2.5-pro", "Gemini 2.5 Pro", Decimal("1.25"), Decimal("10.00")),
        ),
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        label="Anthropic Claude",
        base_url="https://api.anthropic.com/v1",
        docs_url="https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk",
        models=(
            ModelSpec(
                "claude-sonnet-4-5", "Claude Sonnet 4.5", Decimal("3.00"), Decimal("15.00")
            ),
            ModelSpec(
                "claude-haiku-4-5", "Claude Haiku 4.5", Decimal("1.00"), Decimal("5.00")
            ),
        ),
    ),
}


def catalog_view() -> list[dict]:
    return [
        {
            "id": provider.id,
            "label": provider.label,
            "models": [
                {
                    "id": model.id,
                    "label": model.label,
                    "input_per_million_usd": str(model.input_per_million),
                    "output_per_million_usd": str(model.output_per_million),
                }
                for model in provider.models
            ],
            "pricing_updated_at": PRICING_UPDATED_AT,
            "pricing_source": provider.docs_url,
        }
        for provider in PROVIDERS.values()
    ]


def price_for(provider: str, model: str) -> ModelSpec | None:
    spec = PROVIDERS.get(provider)
    return spec.model(model) if spec else None
