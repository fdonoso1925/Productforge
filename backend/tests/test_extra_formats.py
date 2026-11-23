"""Varios formatos en el asistente: el principal + otros que el paquete incluye sí o sí."""

import pytest
from pydantic import ValidationError

from app.content import rules
from app.content.schemas import Format, PackageRequest
from app.pipeline.package import package_request
from tests.fakes import make_item, make_outline, make_request
from tests.test_api_cover import outline_body, outline_ctx


def request_with(*extras: str) -> PackageRequest:
    return PackageRequest.model_validate({**make_request().model_dump(), "extra_formats": extras})


def test_extras_are_optional_and_validated() -> None:
    assert make_request().extra_formats == []
    assert request_with("mind_map", "sheet").extra_formats == [Format.MIND_MAP, Format.SHEET]
    with pytest.raises(ValidationError):
        request_with("sheet", "sheet")  # repetido
    with pytest.raises(ValidationError):
        request_with(make_request().main_format.value)  # el principal no es extra
    with pytest.raises(ValidationError):
        request_with("sheet", "blueprint", "editable_template", "epub")  # 4 pesados: no caben
    with pytest.raises(ValidationError):
        request_with("sheet", "checklist", "planner", "mind_map", "printable", "swipe_file")


def test_the_outline_must_include_every_requested_format() -> None:
    outline = make_outline()  # bumps: sheet, checklist, editable_template; bonus: mind_map, planner
    assert rules.check_package_rules(outline, request_with("sheet", "planner")) == []
    errors = rules.check_package_rules(outline, request_with("blueprint", "printable"))
    assert any("'blueprint'" in e and "como order_bump" in e for e in errors)
    assert any("'printable'" in e and "order_bump o bonus" in e for e in errors)
    fixed = outline.model_copy(
        update={
            "order_bumps": [
                *outline.order_bumps[:2],
                make_item("order_bump", Format.BLUEPRINT, "Plan por fases"),
            ],
            "bonuses": [outline.bonuses[0], make_item("bonus", Format.PRINTABLE, "Hojas", pages=6)],
        }
    )
    assert rules.check_package_rules(fixed, request_with("blueprint", "printable")) == []


def test_the_extras_are_stored_and_read_back_with_the_product() -> None:
    client, llm, repo = outline_ctx()
    llm.responses.append(make_outline())
    body = outline_body(extra_formats=["sheet", "mind_map"])
    response = client.post("/outline", json=body)
    assert response.status_code == 200, response.text
    request = repo.created[-1]["request"]
    assert request.extra_formats == [Format.SHEET, Format.MIND_MAP]
    # Y el prompt de la IA los recibe como formatos obligatorios.
    assert "`sheet`, `mind_map`" in llm.calls[-1].user
    row = {
        "niche": "x" * 3,
        "problem": make_request().problem.model_dump(),
        "market": "es-LATAM",
        "main_format": "pdf_guide",
        "extra_formats": ["sheet"],
    }
    assert package_request(row).extra_formats == [Format.SHEET]
    assert package_request({**row, "extra_formats": None}).extra_formats == []


def test_without_extras_the_ai_chooses_freely() -> None:
    client, llm, _ = outline_ctx()
    llm.responses.append(make_outline())
    assert client.post("/outline", json=outline_body()).status_code == 200
    assert "(além do principal): —." in llm.calls[-1].user
