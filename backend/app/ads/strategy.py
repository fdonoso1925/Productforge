"""Motor de estrategia de creativos: avatares, ángulos, copy, políticas y pre-score.

Reutiliza `ContentService._call` (salida validada con Pydantic, reintento con los errores como
feedback, costo registrado en `ai_usage`) con el system prompt propio del módulo. Todo lo que
dice el usuario o una fuente externa viaja como dato delimitado, nunca como instrucción.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel

from app.ads import rules
from app.ads.schemas import (
    AdaptedBrief,
    AdBrief,
    AdProof,
    AngleProposals,
    AngleSuggestion,
    Avatar,
    AvatarProposals,
    CreativeDraft,
    CreativeDrafts,
    CreativeReviews,
    PolicyVerdict,
    PreScore,
)
from app.content.engines import ContentRejected, ContentService
from app.content.schemas import Market

PLAN_CONCURRENCY = 3
# Un anuncio con observaciones de políticas no se entrega: se corrige y se vuelve a revisar hasta
# que quede en verde. Si tras estas rondas sigue sin pasar, se descarta y se pide uno nuevo.
FIX_ROUNDS = 3
REPLACEMENT_ROUNDS = 2
HEADLINE_WORDS_HINT = rules.IMAGE_HEADLINE_WORDS
SUB_WORDS_HINT = rules.IMAGE_SUB_WORDS


@dataclass
class PlanStats:
    """Cuánto trabajo de políticas hubo que hacer para entregar solo anuncios en verde."""

    fixed: int = 0  # reescrituras hechas para quitar observaciones
    dropped: int = 0  # anuncios descartados por no quedar en verde


class PlannedCreative(BaseModel):
    """Un creativo listo para revisar: copy + semáforo + pre-score."""

    angle_id: str
    avatar: str
    draft: CreativeDraft
    policy: PolicyVerdict
    score: PreScore


def brief_data(brief: AdBrief) -> dict:
    """El brief como dato para la IA. La referencia viaja resumida y sin su URL."""
    data = brief.model_dump(exclude={"reference", "market"})
    if brief.reference is not None:
        data["sales_page_reference"] = brief.reference.model_dump(exclude={"source_url"})
    return {k: v for k, v in data.items() if v not in ("", [], None)}


def proofs_data(proofs: list[AdProof]) -> list[dict]:
    return [p.model_dump(exclude_none=True) for p in proofs]


@dataclass
class AdStrategyService:
    content: ContentService

    def _library(self, market: Market) -> dict[str, dict]:
        return self.content.prompts.angle_library(market)

    def available(self, brief: AdBrief, proofs: list[AdProof]) -> dict[str, dict]:
        return rules.available_angles(
            self._library(brief.market),
            has_proofs=bool(proofs),
            has_price=bool(brief.price_text.strip()),
            real_urgency=bool(brief.real_urgency.strip()),
        )

    async def _call(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        task: str,
        data: dict,
        schema,
        check,
        max_tokens: int,
        model: str | None = None,
    ):
        return await self.content._call(
            user_id=user_id,
            product_id=None,
            market=brief.market,
            task=task,
            data=data,
            schema=schema,
            model=model or self.content.config.model_outline,
            max_tokens=max_tokens,
            check=check,
            system=self.content.prompts.ads_system(brief.market),
        )

    # ── 1. avatares ──

    async def avatars(self, *, user_id: UUID, brief: AdBrief) -> list[Avatar]:
        lo, hi = rules.AVATARS_RANGE

        def check(r: AvatarProposals) -> list[str]:
            errors = [] if lo <= len(r.avatars) <= hi else [f"Devuelve entre {lo} y {hi} avatares."]
            names = [a.name.strip().lower() for a in r.avatars]
            if len(set(names)) != len(names):
                errors.append("Los avatares deben tener nombres distintos.")
            return errors

        result = await self._call(
            user_id=user_id,
            brief=brief,
            task=self.content.prompts.render(brief.market, "ads/avatars"),
            data={"brief": brief_data(brief)},
            schema=AvatarProposals,
            check=check,
            max_tokens=4_000,
        )
        return result.avatars

    # ── 2. ángulos ──

    async def angles(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatars: list[Avatar],
        proofs: list[AdProof],
        winners: list[str] | None = None,
        count: int = 6,
    ) -> list[AngleSuggestion]:
        available = self.available(brief, proofs)
        names = [a.name for a in avatars]
        compact = {
            angle_id: {
                k: v
                for k, v in angle.items()
                if k in ("name", "description", "when", "hook", "needs")
            }
            for angle_id, angle in available.items()
        }
        result = await self._call(
            user_id=user_id,
            brief=brief,
            task=self.content.prompts.render(brief.market, "ads/angles", count=count),
            data={
                "brief": brief_data(brief),
                "avatars": [a.model_dump() for a in avatars],
                "available_angles": compact,
                "winners": [w for w in (winners or []) if w in available],
            },
            schema=AngleProposals,
            check=lambda r: rules.check_angles(r, available.keys(), names),
            max_tokens=3_000,
        )
        return result.angles

    # ── 3. copy de los creativos de un ángulo ──

    async def creatives(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        angle_id: str,
        avatar: Avatar,
        count: int,
        proofs: list[AdProof],
        templates: list[str],
        iterate_from: dict | None = None,
    ) -> list[CreativeDraft]:
        angle = self.available(brief, proofs)[angle_id]
        allowed = [t for t in angle["templates"] if t in templates] or list(templates)
        needs_proof = angle.get("needs") == "proof"

        def check(r: CreativeDrafts) -> list[str]:
            errors = (
                [] if len(r.creatives) == count else [f"Devuelve exactamente {count} variaciones."]
            )
            for i, draft in enumerate(r.creatives):
                errors += [
                    f"creatives[{i}]: {e}"
                    for e in rules.check_draft(
                        draft,
                        allowed_templates=allowed,
                        brief=brief,
                        proofs=proofs,
                        needs_proof=needs_proof,
                    )
                ]
            return errors

        result = await self._call(
            user_id=user_id,
            brief=brief,
            task=self.content.prompts.render(
                brief.market,
                "ads/creatives",
                count=count,
                headline_words=HEADLINE_WORDS_HINT,
                sub_words=SUB_WORDS_HINT,
            ),
            data={
                "brief": brief_data(brief),
                "angle": {
                    "id": angle_id,
                    **{k: angle[k] for k in ("name", "description", "hook", "needs")},
                },
                "avatar": avatar.model_dump(),
                "allowed_templates": allowed,
                "proofs": proofs_data(proofs),
                "real_urgency": brief.real_urgency,
                **({"iterate_from": iterate_from} if iterate_from else {}),
            },
            schema=CreativeDrafts,
            check=check,
            max_tokens=12_000,
            model=self.content.config.model_content,
        )
        return result.creatives

    # ── 4. políticas + pre-score ──

    async def review(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatar: Avatar,
        drafts: list[CreativeDraft],
        proofs: list[AdProof],
    ) -> list[tuple[PolicyVerdict, PreScore]]:
        """Semáforo (reglas + IA, lo peor de los dos) y pre-score de cada creativo."""
        strict = rules.is_sensitive(brief.niche)
        checklist = self.content.prompts.ads_policy(brief.market)

        def check(r: CreativeReviews) -> list[str]:
            got = sorted(x.index for x in r.reviews)
            return (
                []
                if got == list(range(len(drafts)))
                else [
                    f"Devuelve una revisión por cada index de 0 a {len(drafts) - 1}, sin repetir."
                ]
            )

        result = await self._call(
            user_id=user_id,
            brief=brief,
            task=self.content.prompts.render(brief.market, "ads/review", checklist=checklist),
            data={
                "brief": brief_data(brief),
                "avatar": avatar.model_dump(),
                "strict": strict,
                "real_urgency": brief.real_urgency,
                "proofs": proofs_data(proofs),
                "creatives": [{"index": i, **d.model_dump()} for i, d in enumerate(drafts)],
            },
            schema=CreativeReviews,
            check=check,
            max_tokens=8_000,
        )
        by_index = {r.index: r for r in result.reviews}
        out = []
        for i, draft in enumerate(drafts):
            by_rules = rules.policy_verdict(draft, brief, proofs)
            out.append((rules.merge_verdicts(by_rules, by_index[i].policy), by_index[i].score))
        return out

    # ── 5. corregir hasta quedar en verde ──

    async def fix(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatar: Avatar,
        items: list[tuple[CreativeDraft, PolicyVerdict]],
        proofs: list[AdProof],
    ) -> list[CreativeDraft]:
        """Reescribe los creativos con observaciones para que pasen la revisión de políticas.

        Conserva ángulo, plantilla y estructura; el resultado pasa las mismas reglas que el copy
        original (largos, precio y pruebas reales)."""
        n = len(items)

        def check(r: CreativeDrafts) -> list[str]:
            if len(r.creatives) != n:
                return [f"Devuelve exactamente {n} creativos, en el mismo orden."]
            errors: list[str] = []
            for i, (draft, (original, _)) in enumerate(zip(r.creatives, items, strict=True)):
                if draft.template_id != original.template_id:
                    errors.append(f"creatives[{i}]: conserva template_id={original.template_id}.")
                    continue
                errors += [
                    f"creatives[{i}]: {e}"
                    for e in rules.check_draft(
                        draft,
                        allowed_templates=[original.template_id],
                        brief=brief,
                        proofs=proofs,
                        needs_proof=original.proof_id is not None,
                    )
                ]
            return errors

        result = await self._call(
            user_id=user_id,
            brief=brief,
            task=self.content.prompts.render(
                brief.market,
                "ads/fix",
                headline_words=HEADLINE_WORDS_HINT,
                sub_words=SUB_WORDS_HINT,
                checklist=self.content.prompts.ads_policy(brief.market),
            ),
            data={
                "brief": brief_data(brief),
                "avatar": avatar.model_dump(),
                "strict": rules.is_sensitive(brief.niche),
                "real_urgency": brief.real_urgency,
                "proofs": proofs_data(proofs),
                "creatives": [
                    {
                        "index": i,
                        "draft": draft.model_dump(),
                        "policy_notes": [note.model_dump() for note in verdict.notes],
                        "suggested_rewrite": verdict.rewrite,
                    }
                    for i, (draft, verdict) in enumerate(items)
                ],
            },
            schema=CreativeDrafts,
            check=check,
            max_tokens=12_000,
            model=self.content.config.model_content,
        )
        return result.creatives

    async def make_green(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatar: Avatar,
        drafts: list[CreativeDraft],
        proofs: list[AdProof],
        rounds: int,
        stats: PlanStats,
    ) -> list[tuple[CreativeDraft, PolicyVerdict, PreScore]]:
        """Revisa, corrige y vuelve a revisar hasta que todo quede en verde (o se agoten las
        rondas: lo que siga con observaciones se descarta, nunca se entrega)."""
        ok: list[tuple[CreativeDraft, PolicyVerdict, PreScore]] = []
        current = drafts
        pending: list[tuple[CreativeDraft, PolicyVerdict]] = []
        for attempt in range(rounds + 1):
            if not current:
                break
            reviews = await self.review(
                user_id=user_id, brief=brief, avatar=avatar, drafts=current, proofs=proofs
            )
            pending = []
            for draft, (policy, score) in zip(current, reviews, strict=True):
                if policy.status == "green":
                    ok.append((draft, policy, score))
                else:
                    pending.append((draft, policy))
            if not pending:
                return ok
            if attempt == rounds:
                break
            try:
                current = await self.fix(
                    user_id=user_id, brief=brief, avatar=avatar, items=pending, proofs=proofs
                )
            except ContentRejected:
                break  # no se pudo corregir: se descartan
            stats.fixed += len(pending)
        stats.dropped += len(pending)
        return ok

    async def reviewed(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatar: Avatar,
        angle_id: str,
        count: int,
        proofs: list[AdProof],
        templates: list[str],
        stats: PlanStats,
        iterate_from: dict | None = None,
    ) -> list[tuple[CreativeDraft, PolicyVerdict, PreScore]]:
        """Copy + revisión + corrección: devuelve solo creativos en verde (hasta `count`)."""

        async def draft(n: int) -> list[CreativeDraft]:
            return await self.creatives(
                user_id=user_id, brief=brief, angle_id=angle_id, avatar=avatar, count=n,
                proofs=proofs, templates=templates, iterate_from=iterate_from,
            )  # fmt: skip

        green = await self.make_green(
            user_id=user_id, brief=brief, avatar=avatar, drafts=await draft(count),
            proofs=proofs, rounds=FIX_ROUNDS, stats=stats,
        )  # fmt: skip
        if len(green) < count:
            # Los descartados se reponen con creativos nuevos, que pasan por la misma revisión.
            try:
                extra = await draft(count - len(green))
                green += await self.make_green(
                    user_id=user_id, brief=brief, avatar=avatar, drafts=extra,
                    proofs=proofs, rounds=REPLACEMENT_ROUNDS, stats=stats,
                )  # fmt: skip
            except ContentRejected:
                pass
        return green[:count]

    # ── adaptar un lote a otro mercado ──

    async def adapt_brief(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatars: list[Avatar],
        target: Market,
    ) -> tuple[AdBrief, list[Avatar]]:
        """Reescribe (no traduce) brief y avatares con el prompt NATIVO del mercado destino.

        El precio y la urgencia son hechos del usuario: se copian tal cual, la IA no los toca."""
        n = len(avatars)

        def check(r: AdaptedBrief) -> list[str]:
            errors = (
                []
                if len(r.avatars) == n
                else [f"Devuelve exactamente {n} avatares, en el mismo orden."]
            )
            if brief.bonuses and len(r.bonuses) != len(brief.bonuses):
                errors.append("bonuses debe tener la misma cantidad que en source.")
            return errors

        target_brief = brief.model_copy(update={"market": target})
        result = await self._call(
            user_id=user_id,
            brief=target_brief,
            task=self.content.prompts.render(target, "ads/adapt"),
            data={
                "source": {
                    "market": brief.market,
                    **brief_data(brief),
                    "avatars": [a.model_dump() for a in avatars],
                }
            },
            schema=AdaptedBrief,
            check=check,
            max_tokens=5_000,
        )
        adapted = target_brief.model_copy(
            update={
                "niche": result.niche,
                "product_name": result.product_name,
                "problem": result.problem,
                "audience": result.audience,
                "promise": result.promise,
                "bonuses": result.bonuses if brief.bonuses else [],
                "reference": None,  # la página de referencia era de otro mercado
            }
        )
        return adapted, result.avatars

    # ── orquestación de un lote ──

    async def plan(
        self,
        *,
        user_id: UUID,
        brief: AdBrief,
        avatars: list[Avatar],
        picks: list[tuple[str, str, int]],  # (angle_id, nombre del avatar, variaciones)
        proofs: list[AdProof],
        templates: list[str],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
        stats: PlanStats | None = None,
    ) -> list[PlannedCreative]:
        """Copy + revisión de cada ángulo elegido. Un ángulo que falla no tumba el lote."""
        by_name = {a.name: a for a in avatars}
        stats = stats if stats is not None else PlanStats()
        semaphore = asyncio.Semaphore(PLAN_CONCURRENCY)
        done = 0

        async def one(angle_id: str, avatar_name: str, count: int) -> list[PlannedCreative]:
            nonlocal done
            async with semaphore:
                avatar = by_name[avatar_name]
                reviewed = await self.reviewed(
                    user_id=user_id, brief=brief, avatar=avatar, angle_id=angle_id, count=count,
                    proofs=proofs, templates=templates, stats=stats,
                )  # fmt: skip
                done += 1
                if on_progress:
                    await on_progress(done, len(picks))
                return [
                    PlannedCreative(
                        angle_id=angle_id, avatar=avatar_name, draft=d, policy=p, score=s
                    )
                    for d, p, s in reviewed
                ]

        results = await asyncio.gather(*(one(*p) for p in picks), return_exceptions=True)
        planned: list[PlannedCreative] = []
        errors: list[BaseException] = []
        for r in results:
            if isinstance(r, BaseException):
                errors.append(r)
            else:
                planned += r
        if not planned and errors:
            raise errors[0] if not isinstance(errors[0], ContentRejected) else errors[0]
        return planned
