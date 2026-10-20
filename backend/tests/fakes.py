"""Dobles de prueba: IA falsa con respuestas en cola y repositorios en memoria."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.content.claude_client import CallUsage
from app.content.schemas import (
    Format,
    ItemOutline,
    PackageOutline,
    PackageRequest,
    Problem,
)

USAGE = CallUsage("claude-opus-5-5", 1000, 2000, 500, 0)


@dataclass
class Call:
    system: str
    user: str
    schema: type
    model: str
    max_tokens: int
    effort: str


@dataclass
class FakeLLM:
    responses: list[BaseModel | Exception] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    async def structured(self, *, system, user, schema, model, max_tokens, effort):
        self.calls.append(Call(system, user, schema, model, max_tokens, effort))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, schema), f"respuesta {type(response)} no es {schema}"
        return response, USAGE


@dataclass
class FakeUsage:
    records: list[tuple[UUID, UUID | None, CallUsage]] = field(default_factory=list)

    async def record(self, user_id, product_id, usage):
        self.records.append((user_id, product_id, usage))


@dataclass
class FakeProductRepo:
    created: list[dict] = field(default_factory=list)

    async def create_with_outline(self, **kwargs) -> UUID:
        self.created.append(kwargs)
        return uuid4()


def make_problem(**overrides) -> Problem:
    data = {
        "title": "Sair do cheque especial em 60 dias ganhando um salário mínimo",
        "audience": "Trabalhadores CLT com salário mínimo e conta no vermelho",
        "pain": "Todo mês o salário já chega comido pelos juros",
        "promised_result": "Zerar o cheque especial e ter R$ 300 de reserva",
        "timeframe": "60 dias",
        "why_pay": "Os juros custam mais que o produto em uma semana",
        "urgency": 5,
    }
    return Problem(**{**data, **overrides})


def make_request(main_format: Format = Format.PDF_GUIDE, **overrides) -> PackageRequest:
    data = {
        "niche": "Finanças pessoais",
        "problem": make_problem(),
        "market": "pt-BR",
        "main_format": main_format,
    }
    return PackageRequest(**{**data, **overrides})


def make_item(role: str, fmt: Format, title: str, pages: int = 8, **overrides) -> ItemOutline:
    data = {
        "role": role,
        "format": fmt,
        "title": title,
        "promise": f"{title} em 7 dias",
        "objection_addressed": "Não tenho tempo" if role == "bonus" else None,
        "table_of_contents": ["Parte 1", "Parte 2"],
        "estimated_pages": pages,
    }
    return ItemOutline(**{**data, **overrides})


def make_outline(main_format: Format = Format.PDF_GUIDE) -> PackageOutline:
    return PackageOutline(
        product_name="Adeus Cheque Especial",
        main=make_item("main", main_format, "Guia Adeus Cheque Especial", pages=30),
        order_bumps=[
            make_item("order_bump", Format.SHEET, "Planilha Saída do Vermelho"),
            make_item("order_bump", Format.CHECKLIST, "Checklist de Negociação"),
            make_item("order_bump", Format.EDITABLE_TEMPLATE, "Roteiros para o Gerente"),
        ],
        bonuses=[
            make_item("bonus", Format.MIND_MAP, "Mapa da Virada", pages=1),
            make_item("bonus", Format.PLANNER, "Planner 21 Dias", pages=5),
        ],
    )
