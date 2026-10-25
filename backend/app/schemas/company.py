from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TaxRegime = Literal[
    "simples_nacional", "mei", "lucro_presumido", "lucro_real", "nao_informado"
]


class CompanyIdentification(BaseModel):
    legal_name: str | None = Field(default=None, max_length=200)
    trade_name: str | None = Field(default=None, max_length=200)
    cnpj: str | None = Field(default=None, max_length=20)
    branch: Literal["matriz", "filial", "nao_informado"] = "nao_informado"
    registration_status: str | None = Field(default=None, max_length=60)
    inactive_status_acknowledged: bool = False
    status_date: date | None = None
    status_reason: str | None = Field(default=None, max_length=300)
    opened_on: date | None = None
    legal_nature_code: str | None = Field(default=None, max_length=12)
    legal_nature_description: str | None = Field(default=None, max_length=200)
    company_size: str | None = Field(default=None, max_length=80)
    simples_opt_in: bool | None = None
    mei_opt_in: bool | None = None
    state_registration: str | None = Field(default=None, max_length=40)
    municipal_registration: str | None = Field(default=None, max_length=40)

    @field_validator("cnpj")
    @classmethod
    def normalize_cnpj(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return "".join(character for character in value if character.isdigit()) or None


class CompanyActivities(BaseModel):
    primary_cnae_code: str | None = Field(default=None, max_length=12)
    primary_cnae_description: str | None = Field(default=None, max_length=300)
    secondary_cnaes: list[str] = Field(default_factory=list, max_length=100)
    erp_activity: str | None = Field(default=None, max_length=300)
    retail_relevant: bool | None = None
    wholesale_relevant: bool | None = None


class CompanyAddress(BaseModel):
    postal_code: str | None = Field(default=None, max_length=12)
    street: str | None = Field(default=None, max_length=200)
    number: str | None = Field(default=None, max_length=30)
    complement: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    country: str = Field(default="Brasil", max_length=80)

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        return value.strip().upper() if value and value.strip() else None


class CompanyContact(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    business_email: str | None = Field(default=None, max_length=254)


class CompanyFiscalProfile(BaseModel):
    tax_regime: TaxRegime = "nao_informado"
    icms_taxpayer: bool | None = None
    icms_rule: str | None = Field(default=None, max_length=300)
    icms_rate_pct: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    effective_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class CompanyMarketStudyProfile(BaseModel):
    target_margin_pct: Decimal | None = Field(
        default=None, ge=0, lt=100, max_digits=5, decimal_places=2
    )
    channel_commission_pct: Decimal | None = Field(
        default=None, ge=0, lt=100, max_digits=5, decimal_places=2
    )
    fixed_sale_fee: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    outbound_shipping_rule: str | None = Field(default=None, max_length=500)
    expected_return_pct: Decimal | None = Field(
        default=None, ge=0, lt=100, max_digits=5, decimal_places=2
    )
    default_region: str | None = Field(default=None, max_length=80)
    default_category: str | None = Field(default=None, max_length=120)
    presentation_currency: Literal["BRL"] = "BRL"


class CompanyImportProfile(BaseModel):
    enabled: bool | None = None
    radar_modality: str | None = Field(default=None, max_length=120)
    default_incoterm: Literal["FOB", "EXW", "CIF", "nao_informado"] = "nao_informado"
    preferred_mode: Literal["maritimo", "aereo", "nao_informado"] = "nao_informado"
    destination_port: str | None = Field(default=None, max_length=120)
    clearance_state: str | None = Field(default=None, min_length=2, max_length=2)
    exchange_spread_pct: Decimal | None = Field(
        default=None, ge=0, max_digits=5, decimal_places=2
    )
    logistics_operator: str | None = Field(default=None, max_length=200)
    insurance_rule: str | None = Field(default=None, max_length=500)
    terminal_handling_rule: str | None = Field(default=None, max_length=500)
    storage_rule: str | None = Field(default=None, max_length=500)
    domestic_freight_rule: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("clearance_state")
    @classmethod
    def normalize_clearance_state(cls, value: str | None) -> str | None:
        return value.strip().upper() if value and value.strip() else None


class CompanyAddresses(BaseModel):
    fiscal: CompanyAddress = Field(default_factory=CompanyAddress)
    commercial_same_as_fiscal: bool = True
    commercial: CompanyAddress | None = None


class CnpjCardImportMeta(BaseModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_type: Literal["pdf", "jpg", "jpeg", "png"]
    reading: Literal["pdf_text", "ocr"]
    ocr_quality: float | None = None
    retained: Literal[False] = False
    imported_at: datetime


class CompanyProfileData(BaseModel):
    identification: CompanyIdentification = Field(default_factory=CompanyIdentification)
    activities: CompanyActivities = Field(default_factory=CompanyActivities)
    addresses: CompanyAddresses = Field(default_factory=CompanyAddresses)
    contact: CompanyContact = Field(default_factory=CompanyContact)
    fiscal: CompanyFiscalProfile = Field(default_factory=CompanyFiscalProfile)
    market_study: CompanyMarketStudyProfile = Field(default_factory=CompanyMarketStudyProfile)
    import_profile: CompanyImportProfile = Field(default_factory=CompanyImportProfile)
    cnpj_card_import: CnpjCardImportMeta | None = None
    field_sources: dict[str, Literal["manual", "cnpj_card", "official", "default"]] = Field(
        default_factory=dict, max_length=300
    )


class CompanyCompleteness(BaseModel):
    purpose: str
    label: str
    percent: int
    missing: list[str]


class CompanyProfileUpdate(BaseModel):
    revision: int = Field(ge=0)
    data: CompanyProfileData
    manual_fields: list[str] = Field(default_factory=list, max_length=300)


class CompanyProfileOut(BaseModel):
    id: str
    revision: int
    data: CompanyProfileData
    manual_fields: list[str]
    completeness: list[CompanyCompleteness]
    updated_at: datetime | None = None


class CompanyProfileVersionOut(BaseModel):
    id: str
    revision: int
    changed_fields: list[str]
    changed_by: str | None
    created_at: datetime


class CnpjFieldValue(BaseModel):
    value: Any
    confidence: Literal["high", "medium", "low"]
    origin: Literal["cnpj_card"] = "cnpj_card"


class CnpjCardParseOut(BaseModel):
    document: dict[str, Any]
    fields: dict[str, CnpjFieldValue]
    missing: list[str]
    low_confidence: list[str]
    differences: list[dict[str, Any]]
    protected_manual_fields: list[str]
    cnpj_valid: bool
    status_warning: str | None
    lookup_available: bool = False
    lookup_message: str = "Consulta oficial do CNPJ não está configurada."


class CnpjLookupIn(BaseModel):
    cnpj: str = Field(min_length=14, max_length=20)
