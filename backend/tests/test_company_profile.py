from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.permissions import Permission, has_permission
from app.models import CompanyProfileVersion, User, UserRole
from app.schemas.company import CompanyProfileData
from app.services import cnpj_card
from app.services.company_profile import (
    completeness,
    empty_company_data,
    save_company_profile,
    study_company_parameters,
)


def _admin() -> User:
    return User(
        id="company-admin",
        email="company@example.test",
        full_name="Administrador",
        password_hash="not-used",  # noqa: S106 - required test fixture only
        role=UserRole.admin,
    )


def _profile() -> CompanyProfileData:
    data = CompanyProfileData.model_validate(empty_company_data())
    data.identification.legal_name = "Empresa Exemplo Ltda."
    data.identification.cnpj = "11222333000181"
    data.identification.registration_status = "ATIVA"
    data.addresses.fiscal.city = "São Paulo"
    data.addresses.fiscal.state = "SP"
    data.contact.business_email = "contato@example.test"
    data.fiscal.tax_regime = "simples_nacional"
    data.market_study.channel_commission_pct = Decimal("16")
    data.market_study.expected_return_pct = Decimal("2")
    return data


def test_company_profile_is_versioned_snapshot_and_uses_optimistic_revision(db) -> None:
    admin = _admin()
    db.add(admin)
    db.flush()
    first = save_company_profile(
        db,
        admin,
        revision=0,
        data=_profile(),
        manual_fields=["identification.legal_name", "market_study.channel_commission_pct"],
    )
    old_snapshot, missing = study_company_parameters(db)
    first.data = {**first.data, "fiscal": {**first.data["fiscal"], "icms_taxpayer": True}}
    first.revision += 1
    db.commit()
    changed = _profile()
    changed.fiscal.icms_taxpayer = False
    save_company_profile(db, admin, revision=2, data=changed, manual_fields=[])

    versions = db.scalars(select(CompanyProfileVersion).order_by(CompanyProfileVersion.revision))
    history = list(versions)
    assert [version.revision for version in history] == [1, 3]
    assert "fiscal.icms_taxpayer" in history[-1].changed_fields
    assert old_snapshot["fiscal_state"] == "SP"
    assert old_snapshot["target_margin_pct"] == "25"
    assert old_snapshot["profile_version_id"] == history[0].id
    assert missing == []

    with pytest.raises(ValueError, match="outra sessão"):
        save_company_profile(db, admin, revision=2, data=changed, manual_fields=[])


def test_company_completeness_does_not_treat_missing_as_zero(db) -> None:
    rows = completeness(empty_company_data())
    market = next(row for row in rows if row.purpose == "market_study")
    assert market.percent < 100
    assert "regime tributário" in market.missing
    assert "desconhecido" not in " ".join(market.missing)


def test_company_settings_are_admin_only() -> None:
    assert has_permission(UserRole.admin, Permission.SETTINGS_MANAGE)
    assert not has_permission(UserRole.manager, Permission.SETTINGS_MANAGE)


def test_cnpj_check_digits_reject_invented_number() -> None:
    assert cnpj_card.validate_cnpj("11.222.333/0001-81")
    assert not cnpj_card.validate_cnpj("11.222.333/0001-80")
    assert not cnpj_card.validate_cnpj("00000000000000")


def test_card_parser_keeps_only_expected_fields_and_never_returns_personal_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = """
    COMPROVANTE DE INSCRICAO E DE SITUACAO CADASTRAL
    NOME EMPRESARIAL: EMPRESA EXEMPLO LTDA.
    NOME DE FANTASIA: EXEMPLO PARTS
    CNPJ: 11.222.333/0001-81
    MATRIZ
    DATA DE ABERTURA: 01/02/2010
    NATUREZA JURIDICA: 206-2 - Sociedade Empresaria Limitada
    PORTE: DEME
    OPCAO PELO SIMPLES NACIONAL: SIM
    SITUACAO CADASTRAL: ATIVA
    DATA DA SITUACAO CADASTRAL: 10/10/2026
    CNAE PRINCIPAL: 45.30-7-03 - Comercio a varejo de pecas
    LOGRADOURO: RUA EXEMPLO
    NUMERO: 10
    BAIRRO: CENTRO
    MUNICIPIO: SAO PAULO
    UF: SP
    CEP: 01000-000
    TELEFONE: (11) 99999-9999
    EMAIL: CONTATO@EXAMPLE.TEST
    QSA: SOCIO EXEMPLO - CPF 123.456.789-00
    """
    monkeypatch.setattr(cnpj_card, "_read_text", lambda *_: (text, "pdf_text"))
    result = cnpj_card.parse_card(
        "cartao.pdf",
        b"%PDF-test",
        current_data=empty_company_data(),
        manual_fields=[],
    )
    serialized = str(result)
    assert result["fields"]["identification.cnpj"]["value"] == "11222333000181"
    assert result["fields"]["identification.legal_name"]["value"] == "EMPRESA EXEMPLO LTDA."
    assert result["fields"]["addresses.fiscal.state"]["value"] == "SP"
    assert "socio" not in serialized.casefold()
    assert "123.456.789-00" not in serialized
    assert result["document"]["retained"] is False


def test_cnpj_lookup_is_explicitly_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cnpj_card,
        "_read_text",
        lambda *_: ("CNPJ: 11.222.333/0001-81\nNOME EMPRESARIAL: TESTE\n", "pdf_text"),
    )
    result = cnpj_card.parse_card(
        "cartao.pdf",
        b"%PDF-test",
        current_data=empty_company_data(),
        manual_fields=[],
    )
    assert result["lookup_available"] is False
    assert "não está configurada" in result["lookup_message"]
