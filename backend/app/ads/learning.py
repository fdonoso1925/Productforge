"""Aprendizaje a partir de los resultados cargados: qué ángulos, plantillas y hooks rinden mejor.

Todo se calcula de los TOTALES (no de promedios de promedios) y solo se compara lo que tiene datos
suficientes. La app no promete ganadores: resume lo que pasó con tu dinero y propone repetirlo.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

MIN_IMPRESSIONS = 1000  # con menos, el CTR y el resto son ruido
TOP_WINNERS = 3
Row = dict


@dataclass
class Metrics:
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    purchases: int = 0
    revenue: float = 0.0

    def add(self, result: Row) -> None:
        self.spend += float(result.get("spend") or 0)
        self.impressions += int(result.get("impressions") or 0)
        self.clicks += int(result.get("clicks") or 0)
        self.purchases += int(result.get("purchases") or 0)
        self.revenue += float(result.get("revenue") or 0)

    @property
    def ctr(self) -> float | None:
        """Porcentaje de clics sobre impresiones."""
        return round(100 * self.clicks / self.impressions, 2) if self.impressions else None

    @property
    def cpc(self) -> float | None:
        return round(self.spend / self.clicks, 2) if self.clicks else None

    @property
    def cpa(self) -> float | None:
        return round(self.spend / self.purchases, 2) if self.purchases else None

    @property
    def roas(self) -> float | None:
        return round(self.revenue / self.spend, 2) if self.spend and self.revenue else None

    @property
    def enough_data(self) -> bool:
        return self.impressions >= MIN_IMPRESSIONS

    def as_dict(self) -> dict:
        return {
            "spend": round(self.spend, 2),
            "impressions": self.impressions,
            "clicks": self.clicks,
            "purchases": self.purchases,
            "revenue": round(self.revenue, 2),
            "ctr": self.ctr,
            "cpc": self.cpc,
            "cpa": self.cpa,
            "roas": self.roas,
            "enough_data": self.enough_data,
        }


def aggregate(results: Iterable[Row], key: Callable[[Row], str | None]) -> dict[str, Metrics]:
    """Suma los resultados por clave (ángulo, plantilla, creativo…). Las claves nulas se ignoran."""
    totals: dict[str, Metrics] = defaultdict(Metrics)
    for result in results:
        k = key(result)
        if k:
            totals[k].add(result)
    return dict(totals)


@dataclass
class Ranking:
    metric: str  # roas | cpa | ctr | none
    order: list[str] = field(default_factory=list)
    winners: list[str] = field(default_factory=list)


def rank(items: dict[str, Metrics]) -> Ranking:
    """Ordena por la mejor métrica DISPONIBLE y marca los ganadores.

    - Si algo con datos suficientes tiene compras: ROAS (si todos tienen valor de conversión) o,
      si no, CPA (más bajo es mejor). Lo que no vendió queda detrás.
    - Si nadie vendió: CTR.
    - Lo que no tiene datos suficientes nunca gana; va al final, por gasto.
    """
    eligible = {k: m for k, m in items.items() if m.enough_data}
    rest = sorted(set(items) - set(eligible), key=lambda k: -items[k].spend)
    sold = {k: m for k, m in eligible.items() if m.purchases > 0}

    if sold:
        use_roas = all(m.roas is not None for m in sold.values())
        metric = "roas" if use_roas else "cpa"
        ordered_sold = sorted(
            sold,
            key=lambda k: (-(sold[k].roas or 0)) if use_roas else (sold[k].cpa or float("inf")),
        )
        unsold = sorted(
            (k for k in eligible if k not in sold), key=lambda k: -(eligible[k].ctr or 0)
        )
        return Ranking(metric, [*ordered_sold, *unsold, *rest], ordered_sold[:TOP_WINNERS])

    if eligible:
        ordered = sorted(eligible, key=lambda k: -(eligible[k].ctr or 0))
        winners = [k for k in ordered if (eligible[k].ctr or 0) > 0][:TOP_WINNERS]
        return Ranking("ctr", [*ordered, *rest], winners)

    return Ranking("none", rest, [])


def build_insights(creatives: list[Row], results: list[Row], batches: dict[str, Row]) -> dict:
    """Panel de aprendizaje: ángulos, plantillas y creativos con sus métricas y ganadores.

    `creatives` y `batches` ya vienen filtrados por mercado y nicho."""
    by_creative = {c["id"]: c for c in creatives if c["status"] != "discarded"}
    used = [r for r in results if r["creative_id"] in by_creative]

    def block(key: Callable[[Row], str | None]) -> dict:
        totals = aggregate(used, key)
        ranking = rank(totals)
        return {"metric": ranking.metric, "totals": totals, "ranking": ranking}

    angle = block(lambda r: by_creative[r["creative_id"]]["angle"])
    template = block(lambda r: by_creative[r["creative_id"]]["template_id"])
    # Un borrador compone varios formatos con el mismo texto: el «hook» se mide por grupo.
    hooks = block(lambda r: by_creative[r["creative_id"]]["group_id"])
    group_lead = {}
    for c in by_creative.values():
        group_lead.setdefault(c["group_id"], c)

    def rows(section: dict, extra: Callable[[str], dict]) -> list[dict]:
        ranking: Ranking = section["ranking"]
        out = []
        for position, key in enumerate(ranking.order, start=1):
            out.append(
                {
                    "key": key,
                    "rank": position,
                    "winner": key in ranking.winners,
                    **section["totals"][key].as_dict(),
                    **extra(key),
                }
            )
        return out

    def hook_info(group: str) -> dict:
        lead = group_lead[group]
        draft = lead["copy"]
        return {
            "creative_id": lead["id"],
            "headline": draft["image"]["headline"],
            "ad_headline": draft["ad"]["headline"],
            "angle": lead["angle"],
            "template_id": lead["template_id"],
            "filename": lead["filename"],
        }

    total = Metrics()
    for r in used:
        total.add(r)
    return {
        "totals": total.as_dict(),
        "creatives_with_results": len({r["creative_id"] for r in used}),
        "min_impressions": MIN_IMPRESSIONS,
        "angles": {"metric": angle["metric"], "items": rows(angle, lambda _: {})},
        "templates": {"metric": template["metric"], "items": rows(template, lambda _: {})},
        "hooks": {"metric": hooks["metric"], "items": rows(hooks, hook_info)},
        "winner_angles": angle["ranking"].winners,
    }
