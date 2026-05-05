"""Testkampagnen-API (Block 0022).

Lesen ist auth-only; Schreiben CSRF + Service-Permission.
``TestCampaignService`` kapselt die Berechtigungslogik (Admin oder
WP-Lead aller beteiligten WPs).

Es gibt **keinen** Hard-Delete und **keinen** Datei-Upload — Dokumente
werden ausschließlich über das bestehende Dokumentenregister verlinkt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ref4ep.api.deps import (
    get_audit_logger,
    get_current_person,
    get_session,
    require_csrf,
)
from ref4ep.api.schemas.campaigns import (
    CampaignCreateRequest,
    CampaignDetailOut,
    CampaignDocumentLinkAddRequest,
    CampaignDocumentOut,
    CampaignListItemOut,
    CampaignParticipantAddRequest,
    CampaignParticipantOut,
    CampaignParticipantPatchRequest,
    CampaignPatchRequest,
    CampaignPersonOut,
    CampaignWorkpackageOut,
)
from ref4ep.domain.models import Person, TestCampaign, TestCampaignParticipant
from ref4ep.services.audit_logger import AuditLogger
from ref4ep.services.test_campaign_service import TestCampaignService

router = APIRouter(prefix="/api")

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[Person, Depends(get_current_person)]
AuditDep = Annotated[AuditLogger, Depends(get_audit_logger)]


def _service(
    session: Session, actor: Person, *, audit: AuditLogger | None = None
) -> TestCampaignService:
    return TestCampaignService(
        session,
        role=actor.platform_role,
        person_id=actor.id,
        audit=audit,
    )


def _person_out(person: Person) -> CampaignPersonOut:
    return CampaignPersonOut(id=person.id, display_name=person.display_name, email=person.email)


def _wps_out(campaign: TestCampaign) -> list[CampaignWorkpackageOut]:
    return [
        CampaignWorkpackageOut(code=link.workpackage.code, title=link.workpackage.title)
        for link in sorted(campaign.workpackage_links, key=lambda link: link.workpackage.sort_order)
    ]


def _participant_out(participant: TestCampaignParticipant) -> CampaignParticipantOut:
    return CampaignParticipantOut(
        id=participant.id,
        person=_person_out(participant.person),
        role=participant.role,
        note=participant.note,
    )


def _document_out(link) -> CampaignDocumentOut:
    return CampaignDocumentOut(
        document_id=link.document_id,
        title=link.document.title,
        deliverable_code=link.document.deliverable_code,
        workpackage_code=link.document.workpackage.code if link.document.workpackage else None,
        label=link.label,
    )


def _list_item(campaign: TestCampaign, *, can_edit: bool) -> CampaignListItemOut:
    return CampaignListItemOut(
        id=campaign.id,
        code=campaign.code,
        title=campaign.title,
        category=campaign.category,
        status=campaign.status,
        starts_on=campaign.starts_on,
        ends_on=campaign.ends_on,
        facility=campaign.facility,
        workpackages=_wps_out(campaign),
        participants_count=len(campaign.participant_links),
        documents_count=len(campaign.document_links),
        can_edit=can_edit,
    )


def _detail(campaign: TestCampaign, *, can_edit: bool) -> CampaignDetailOut:
    return CampaignDetailOut(
        id=campaign.id,
        code=campaign.code,
        title=campaign.title,
        category=campaign.category,
        status=campaign.status,
        starts_on=campaign.starts_on,
        ends_on=campaign.ends_on,
        facility=campaign.facility,
        location=campaign.location,
        short_description=campaign.short_description,
        objective=campaign.objective,
        test_matrix=campaign.test_matrix,
        expected_measurements=campaign.expected_measurements,
        boundary_conditions=campaign.boundary_conditions,
        success_criteria=campaign.success_criteria,
        risks_or_open_points=campaign.risks_or_open_points,
        created_by=_person_out(campaign.created_by),
        workpackages=_wps_out(campaign),
        participants=[_participant_out(p) for p in campaign.participant_links],
        documents=[_document_out(d) for d in campaign.document_links],
        can_edit=can_edit,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": str(exc)}},
        )
    if isinstance(exc, LookupError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": str(exc)}},
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": {"code": "invalid", "message": str(exc)}},
        )
    raise exc


# ---- Kampagnen --------------------------------------------------------


@router.get("/campaigns", response_model=list[CampaignListItemOut])
def list_campaigns(
    actor: ActorDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    workpackage: str | None = None,
    q: str | None = None,
) -> list[CampaignListItemOut]:
    service = _service(session, actor)
    try:
        campaigns = service.list_campaigns(
            status=status_filter,
            category=category,
            workpackage_code=workpackage,
            q=q,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    return [_list_item(c, can_edit=service.can_edit_campaign(c)) for c in campaigns]


@router.post(
    "/campaigns",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_campaign(
    payload: CampaignCreateRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        campaign = service.create_campaign(
            code=payload.code,
            title=payload.title,
            category=payload.category,
            status=payload.status,
            starts_on=payload.starts_on,
            ends_on=payload.ends_on,
            facility=payload.facility,
            location=payload.location,
            short_description=payload.short_description,
            objective=payload.objective,
            test_matrix=payload.test_matrix,
            expected_measurements=payload.expected_measurements,
            boundary_conditions=payload.boundary_conditions,
            success_criteria=payload.success_criteria,
            risks_or_open_points=payload.risks_or_open_points,
            workpackage_ids=payload.workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(campaign, can_edit=True)


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(campaign_id: str, actor: ActorDep, session: SessionDep) -> CampaignDetailOut:
    service = _service(session, actor)
    campaign = service.get(campaign_id)
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Testkampagne nicht gefunden."}},
        )
    return _detail(campaign, can_edit=service.can_edit_campaign(campaign))


@router.patch(
    "/campaigns/{campaign_id}",
    response_model=CampaignDetailOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign(
    campaign_id: str,
    payload: CampaignPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    raw = payload.model_dump(exclude_unset=True)
    workpackage_ids = raw.pop("workpackage_ids", None)
    try:
        campaign = service.update_campaign(
            campaign_id,
            fields=raw,
            workpackage_ids=workpackage_ids,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(campaign, can_edit=True)


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=CampaignDetailOut,
    dependencies=[Depends(require_csrf)],
)
def cancel_campaign(
    campaign_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        campaign = service.cancel_campaign(campaign_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _detail(campaign, can_edit=True)


# ---- Teilnehmende -----------------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/participants",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def add_campaign_participant(
    campaign_id: str,
    payload: CampaignParticipantAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_participant(
            campaign_id,
            person_id=payload.person_id,
            role=payload.role,
            note=payload.note,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    campaign = service.get(campaign_id)
    return _detail(campaign, can_edit=True)


@router.patch(
    "/campaign-participants/{participant_id}",
    response_model=CampaignParticipantOut,
    dependencies=[Depends(require_csrf)],
)
def patch_campaign_participant(
    participant_id: str,
    payload: CampaignParticipantPatchRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignParticipantOut:
    service = _service(session, actor, audit=audit)
    fields = payload.model_dump(exclude_unset=True)
    try:
        participant = service.update_participant(participant_id, fields=fields)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return _participant_out(participant)


@router.delete(
    "/campaign-participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def remove_campaign_participant(
    participant_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_participant(participant_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Dokumentverknüpfungen --------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/documents",
    response_model=CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def link_campaign_document(
    campaign_id: str,
    payload: CampaignDocumentLinkAddRequest,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> CampaignDetailOut:
    service = _service(session, actor, audit=audit)
    try:
        service.add_document_link(campaign_id, document_id=payload.document_id, label=payload.label)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    campaign = service.get(campaign_id)
    return _detail(campaign, can_edit=True)


@router.delete(
    "/campaigns/{campaign_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def unlink_campaign_document(
    campaign_id: str,
    document_id: str,
    actor: ActorDep,
    session: SessionDep,
    audit: AuditDep,
) -> Response:
    service = _service(session, actor, audit=audit)
    try:
        service.remove_document_link(campaign_id, document_id)
    except Exception as exc:  # noqa: BLE001
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
