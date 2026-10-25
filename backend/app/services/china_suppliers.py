from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class SupplierSearchResult:
    status: str
    message: str
    source: str = "alibaba"
    leads: list[dict[str, Any]] = field(default_factory=list)


class ChinaSupplierProvider(Protocol):
    def search(self, candidates: list[dict[str, Any]]) -> SupplierSearchResult: ...


class UnavailableChinaSupplierProvider:
    """Explicit state used until Alibaba/1688 API authorization is contracted."""

    source = "alibaba"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or (
            "A busca de fornecedores na China está indisponível: configure uma API "
            "licenciada do Alibaba e a base fiscal aplicável. Nenhum fornecedor ou preço "
            "foi pesquisado."
        )

    def search(self, candidates: list[dict[str, Any]]) -> SupplierSearchResult:
        return SupplierSearchResult(status="unavailable", message=self.message, leads=[])


class FixtureChinaSupplierProvider:
    """Test/HML adapter. Fixtures must be visibly identified and never marketed as real."""

    source = "fixture"

    def __init__(self, leads: list[dict[str, Any]] | None = None) -> None:
        self.leads = leads or []

    def search(self, candidates: list[dict[str, Any]]) -> SupplierSearchResult:
        if not self.leads:
            return SupplierSearchResult(
                status="unavailable",
                message=(
                    "A fonte de fornecedores está em modo de fixture, sem registros. "
                    "Nenhuma empresa ou cotação real foi pesquisada."
                ),
                source=self.source,
            )
        return SupplierSearchResult(
            status="fixture",
            message="Dados de demonstração; não representam fornecedores ou preços reais.",
            source=self.source,
            leads=self.leads,
        )


def china_supplier_provider() -> ChinaSupplierProvider:
    settings = get_settings()
    mode = getattr(settings, "china_supplier_mode", "disabled")
    if settings.app_env != "production" and mode == "fixture":
        return FixtureChinaSupplierProvider()
    return UnavailableChinaSupplierProvider()
