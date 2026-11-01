"""HTTP routes for deterministic rules-as-code checks."""

from decimal import Decimal

from fastapi import APIRouter

from wetvia.api.schemas.rules import DakkapelRuleRequest, DakkapelRuleResponse
from wetvia.rules import DakkapelInvoer, toets

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.post("/dakkapel", response_model=DakkapelRuleResponse)
async def check_dakkapel(request: DakkapelRuleRequest) -> DakkapelRuleResponse:
    """Map validated HTTP input to the public pure rules API."""
    invoer = DakkapelInvoer(
        dakvlak=request.dakvlak,
        dakvlak_naar_openbaar_toegankelijk_gebied=(
            request.dakvlak_naar_openbaar_toegankelijk_gebied
        ),
        plat_dak=request.plat_dak,
        hoogte_m=_decimal_or_none(request.hoogte_m),
        onderzijde_boven_dakvoet_m=_decimal_or_none(request.onderzijde_boven_dakvoet_m),
        bovenzijde_onder_daknok_m=_decimal_or_none(request.bovenzijde_onder_daknok_m),
        linker_zijkant_tot_dakvlakrand_m=_decimal_or_none(request.linker_zijkant_tot_dakvlakrand_m),
        rechter_zijkant_tot_dakvlakrand_m=_decimal_or_none(
            request.rechter_zijkant_tot_dakvlakrand_m
        ),
        monumentrelatie=request.monumentrelatie,
        gebiedsbescherming=request.gebiedsbescherming,
    )
    result = toets(invoer)
    return DakkapelRuleResponse.model_validate(result, from_attributes=True)


def _decimal_or_none(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


__all__ = ["router"]
