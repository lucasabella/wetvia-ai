"""Routes for downloadable dakkapel concept dossiers."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request, Response, status

from wetvia.api.schemas.dossier import DakkapelDossierRequest
from wetvia.dossier import DakkapelDossierService, DossierFormat
from wetvia.rules import DakkapelInvoer

router = APIRouter(prefix="/api/dossier", tags=["dossier"])

_MEASUREMENT_FIELDS = (
    "hoogte_m",
    "onderzijde_boven_dakvoet_m",
    "bovenzijde_onder_daknok_m",
    "linker_zijkant_tot_dakvlakrand_m",
    "rechter_zijkant_tot_dakvlakrand_m",
)
_BINARY_RESPONSE = {
    "description": "Generated concept dossier attachment.",
    "content": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
            "schema": {"type": "string", "format": "binary"}
        },
        "application/pdf": {"schema": {"type": "string", "format": "binary"}},
        "text/markdown": {"schema": {"type": "string", "format": "binary"}},
    },
}


@router.post(
    "/dakkapel",
    response_class=Response,
    responses={
        200: _BINARY_RESPONSE,
        503: {"description": "The local dossier description provider is unavailable."},
    },
)
async def generate_dakkapel_dossier(
    request: Request,
    payload: DakkapelDossierRequest,
    format: DossierFormat,
) -> Response:
    service: DakkapelDossierService | None = getattr(request.app.state, "dossier_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dossier generation is not configured with a local description model.",
        )

    facts = _to_domain_input(payload)
    try:
        attachment = await service.create_attachment(
            facts,
            location=payload.locatie,
            format=format,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The concept dossier could not be generated.",
        ) from exc
    return Response(
        content=attachment.content,
        media_type=attachment.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _to_domain_input(payload: DakkapelDossierRequest) -> DakkapelInvoer:
    values = payload.invoer.model_dump()
    for field in _MEASUREMENT_FIELDS:
        value = values[field]
        values[field] = None if value is None else Decimal(value)
    return DakkapelInvoer(**values)


__all__ = ["router"]
