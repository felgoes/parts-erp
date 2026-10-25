import subprocess

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import CompanyProfile, CompanyProfileVersion, User
from app.schemas.company import (
    CnpjCardParseOut,
    CnpjLookupIn,
    CompanyProfileOut,
    CompanyProfileUpdate,
    CompanyProfileVersionOut,
)
from app.services.cnpj_card import parse_card
from app.services.company_profile import (
    completeness,
    empty_company_data,
    get_company_profile,
    profile_data,
    save_company_profile,
)

router = APIRouter(prefix="/settings/company", tags=["Cadastro da empresa"])


def _output(profile: CompanyProfile | None) -> CompanyProfileOut:
    data = profile_data(profile)
    raw = data.model_dump(mode="json")
    return CompanyProfileOut(
        id="active",
        revision=profile.revision if profile else 0,
        data=data,
        manual_fields=profile.manual_fields if profile else [],
        completeness=completeness(raw),
        updated_at=profile.updated_at if profile else None,
    )


@router.get("", response_model=CompanyProfileOut)
def read_company_profile(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> CompanyProfileOut:
    return _output(get_company_profile(db))


@router.put("", response_model=CompanyProfileOut)
def update_company_profile(
    payload: CompanyProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> CompanyProfileOut:
    try:
        profile = save_company_profile(
            db,
            user,
            revision=payload.revision,
            data=payload.data,
            manual_fields=payload.manual_fields,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _output(profile)


@router.get("/history", response_model=list[CompanyProfileVersionOut])
def company_profile_history(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> list[CompanyProfileVersionOut]:
    versions = db.scalars(
        select(CompanyProfileVersion)
        .where(CompanyProfileVersion.profile_id == "active")
        .order_by(CompanyProfileVersion.revision.desc())
        .limit(50)
    ).all()
    return [
        CompanyProfileVersionOut(
            id=version.id,
            revision=version.revision,
            changed_fields=version.changed_fields,
            changed_by=version.changed_by.full_name if version.changed_by else None,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.post("/cnpj-card/parse", response_model=CnpjCardParseOut)
def parse_company_card(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict:
    content = file.file.read(10 * 1024 * 1024 + 1)
    try:
        profile = get_company_profile(db)
        return parse_card(
            file.filename or "",
            content,
            current_data=profile.data if profile else empty_company_data(),
            manual_fields=profile.manual_fields if profile else [],
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()


@router.post("/cnpj-lookup")
def lookup_company_cnpj(
    payload: CnpjLookupIn,
    _: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> dict[str, object]:
    raise HTTPException(
        status_code=503,
        detail=(
            "Consulta oficial do CNPJ não está configurada. "
            "Importe o Cartão CNPJ ou preencha os dados manualmente."
        ),
    )
