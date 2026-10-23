"""Panel de aprendizaje: junta lotes, creativos y resultados del usuario y calcula los ganadores."""

from uuid import UUID

from app.ads.learning import build_insights


def _same(a: str | None, b: str | None) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold()


async def load_insights(
    *,
    batches,
    creatives,
    results,
    user_id: UUID,
    market: str | None = None,
    niche: str | None = None,
) -> dict:
    """Aprendizaje de los lotes del usuario, filtrado por mercado y nicho (opcionales)."""
    all_batches = await batches.list_for_user(user_id, limit=500)
    chosen = {
        b["id"]: b
        for b in all_batches
        if (not market or b["market"] == market) and (not niche or _same(b["niche"], niche))
    }
    mine = [c for c in await creatives.list_for_user(user_id) if c["batch_id"] in chosen]
    return build_insights(mine, await results.list_for_user(user_id), chosen)


async def winner_angles(
    *, batches, creatives, results, user_id: UUID, market: str, niche: str
) -> list[str]:
    """Ángulos ganadores para un lote nuevo: los del mismo nicho y mercado; si ese nicho aún no
    tiene datos suficientes, los del mercado."""
    common = {"batches": batches, "creatives": creatives, "results": results, "user_id": user_id}
    exact = await load_insights(**common, market=market, niche=niche)
    if exact["winner_angles"]:
        return exact["winner_angles"]
    return (await load_insights(**common, market=market))["winner_angles"]
