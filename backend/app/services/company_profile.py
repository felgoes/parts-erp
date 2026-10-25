from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyProfile, CompanyProfileVersion, User
from app.schemas.company import CompanyCompleteness, CompanyProfileData

MISSING = object()


def empty_company_data() -> dict[str, Any]:
    return CompanyProfileData(
        market_study={
            "target_margin_pct": "25",
            "presentation_currency": "BRL",
        },
        import_profile={"exchange_spread_pct": "3"},
        field_sources={
            "market_study.target_margin_pct": "default",
            "import_profile.exchange_spread_pct": "default",
        },
    ).model_dump(mode="json")


def _read(profile: dict[str, Any], dotted: str) -> Any:
    value: Any = profile
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def _has(profile: dict[str, Any], dotted: str) -> bool:
    value = _read(profile, dotted)
    return value is not MISSING and value not in (None, "", [], {}, "nao_informado")


def _percent(profile: dict[str, Any], fields: list[str]) -> int:
    return round(sum(_has(profile, field) for field in fields) / len(fields) * 100)


REQUIREMENTS: dict[str, tuple[str, list[str]]] = {
    "minimum": (
        "Mínima",
        [
            "identification.legal_name",
            "identification.cnpj",
            "identification.registration_status",
            "addresses.fiscal.city",
            "addresses.fiscal.state",
            "contact.business_email",
        ],
    ),
    "market_study": (
        "Estudo de mercado",
        [
            "identification.legal_name",
            "identification.cnpj",
            "addresses.fiscal.state",
            "fiscal.tax_regime",
            "market_study.target_margin_pct",
            "market_study.channel_commission_pct",
            "market_study.expected_return_pct",
        ],
    ),
    "import": (
        "Importação",
        [
            "addresses.fiscal.state",
            "fiscal.tax_regime",
            "import_profile.enabled",
            "import_profile.default_incoterm",
            "import_profile.preferred_mode",
            "import_profile.clearance_state",
            "import_profile.exchange_spread_pct",
        ],
    ),
    "invoicing": (
        "Faturamento",
        [
            "identification.legal_name",
            "identification.cnpj",
            "identification.state_registration",
            "addresses.fiscal.city",
            "addresses.fiscal.state",
            "fiscal.tax_regime",
        ],
    ),
}


LABELS = {
    "identification.legal_name": "razão social",
    "identification.cnpj": "CNPJ",
    "identification.registration_status": "situação cadastral",
    "identification.state_registration": "inscrição estadual",
    "addresses.fiscal.city": "município fiscal",
    "addresses.fiscal.state": "UF fiscal",
    "contact.business_email": "e-mail empresarial",
    "fiscal.tax_regime": "regime tributário",
    "market_study.target_margin_pct": "margem-alvo",
    "market_study.channel_commission_pct": "comissão do canal",
    "market_study.expected_return_pct": "percentual de devolução",
    "import_profile.enabled": "habilitação para importar",
    "import_profile.default_incoterm": "Incoterm",
    "import_profile.preferred_mode": "modal de importação",
    "import_profile.clearance_state": "UF de desembaraço",
    "import_profile.exchange_spread_pct": "spread cambial",
}


def completeness(profile: dict[str, Any]) -> list[CompanyCompleteness]:
    result: list[CompanyCompleteness] = []
    for purpose, (label, fields) in REQUIREMENTS.items():
        missing = [LABELS.get(field, field) for field in fields if not _has(profile, field)]
        result.append(
            CompanyCompleteness(
                purpose=purpose,
                label=label,
                percent=_percent(profile, fields),
                missing=missing,
            )
        )
    return result


def get_company_profile(db: Session) -> CompanyProfile | None:
    return db.get(CompanyProfile, "active")


def profile_data(profile: CompanyProfile | None) -> CompanyProfileData:
    return CompanyProfileData.model_validate(profile.data if profile else empty_company_data())


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(child, dict):
                flattened.update(_flatten(child, path))
            else:
                flattened[path] = child
    return flattened


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    old, new = _flatten(before), _flatten(after)
    return sorted(
        key for key in set(old) | set(new) if old.get(key, MISSING) != new.get(key, MISSING)
    )


def save_company_profile(
    db: Session,
    user: User,
    *,
    revision: int,
    data: CompanyProfileData,
    manual_fields: list[str],
) -> CompanyProfile:
    current = db.scalar(
        select(CompanyProfile).where(CompanyProfile.id == "active").with_for_update()
    )
    current_revision = current.revision if current else 0
    if revision != current_revision:
        raise ValueError(
            "O cadastro foi alterado em outra sessão. Recarregue antes de salvar novamente."
        )
    if data.identification.cnpj:
        from app.services.cnpj_card import validate_cnpj

        if not validate_cnpj(data.identification.cnpj):
            raise ValueError("O CNPJ informado não tem dígitos verificadores válidos.")
    status = (data.identification.registration_status or "").strip().casefold()
    if (
        status
        and status not in {"ativa", "ativo"}
        and not data.identification.inactive_status_acknowledged
    ):
        raise ValueError(
            "A situação cadastral não está ativa. Confirme explicitamente essa decisão "
            "antes de salvar."
        )
    before = deepcopy(current.data) if current else empty_company_data()
    serialized = data.model_dump(mode="json")
    changes = changed_fields(before, serialized)
    if current is None:
        current = CompanyProfile(
            id="active",
            revision=0,
            data=before,
            manual_fields=[],
        )
        db.add(current)
        db.flush()
    current.data = serialized
    current.manual_fields = sorted(set(manual_fields))
    current.revision += 1
    db.add(
        CompanyProfileVersion(
            id=str(uuid4()),
            profile_id=current.id,
            revision=current.revision,
            data=deepcopy(serialized),
            manual_fields=current.manual_fields,
            changed_fields=changes,
            changed_by_id=user.id,
        )
    )
    db.commit()
    db.refresh(current)
    return current


def study_company_parameters(db: Session) -> tuple[dict[str, Any], list[str]]:
    profile = get_company_profile(db)
    if not profile:
        return {}, ["cadastro da empresa"]
    data = profile_data(profile)
    required = list(REQUIREMENTS["market_study"][1])
    missing = [LABELS.get(field, field) for field in required if not _has(profile.data, field)]
    version_id = db.scalar(
        select(CompanyProfileVersion.id).where(
            CompanyProfileVersion.profile_id == profile.id,
            CompanyProfileVersion.revision == profile.revision,
        )
    )
    snapshot = {
        "profile_version_id": version_id,
        "profile_revision": profile.revision,
        "fiscal_state": data.addresses.fiscal.state,
        "tax_regime": data.fiscal.tax_regime,
        "icms_taxpayer": data.fiscal.icms_taxpayer,
        "target_margin_pct": (
            str(data.market_study.target_margin_pct)
            if data.market_study.target_margin_pct is not None
            else None
        ),
        "channel_commission_pct": (
            str(data.market_study.channel_commission_pct)
            if data.market_study.channel_commission_pct is not None
            else None
        ),
        "fixed_sale_fee": (
            str(data.market_study.fixed_sale_fee)
            if data.market_study.fixed_sale_fee is not None
            else None
        ),
        "outbound_shipping_rule": data.market_study.outbound_shipping_rule,
        "expected_return_pct": (
            str(data.market_study.expected_return_pct)
            if data.market_study.expected_return_pct is not None
            else None
        ),
        "import_enabled": data.import_profile.enabled,
        "default_incoterm": data.import_profile.default_incoterm,
        "preferred_mode": data.import_profile.preferred_mode,
        "clearance_state": data.import_profile.clearance_state,
        "exchange_spread_pct": (
            str(data.import_profile.exchange_spread_pct)
            if data.import_profile.exchange_spread_pct is not None
            else None
        ),
    }
    return snapshot, missing
