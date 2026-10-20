from app.content.rules import check_content_rules, check_package_rules
from app.content.schemas import Format
from app.content.schemas.formats import (
    Column,
    Computation,
    Concept,
    ConceptMapContent,
    EditableTemplateContent,
    PlannerContent,
    PlannerDay,
    Relation,
    SheetContent,
    SheetTab,
)
from tests.fakes import make_item, make_outline, make_request


def test_valid_outline_passes() -> None:
    assert check_package_rules(make_outline(), make_request()) == []


def test_main_format_must_match_request() -> None:
    errors = check_package_rules(make_outline(), make_request(main_format=Format.EPUB))
    assert any("main.format" in e for e in errors)


def test_main_page_range() -> None:
    outline = make_outline()
    outline.main.estimated_pages = 12
    assert any("estimated_pages" in e for e in check_package_rules(outline, make_request()))


def test_needs_three_bumps_and_two_bonuses() -> None:
    outline = make_outline()
    outline.order_bumps.pop()
    outline.bonuses.pop()
    errors = check_package_rules(outline, make_request())
    assert any("order_bumps" in e for e in errors)
    assert any("bonuses" in e for e in errors)


def test_bump_formats_distinct_and_not_main() -> None:
    outline = make_outline()
    outline.order_bumps[1] = make_item("order_bump", Format.SHEET, "Outra planilha")
    outline.order_bumps[2] = make_item("order_bump", Format.PDF_GUIDE, "Mini guia")
    errors = check_package_rules(outline, make_request())
    assert any("distinto a los demás" in e for e in errors)
    assert any("mismo formato que el producto principal" in e for e in errors)


def test_bonus_must_be_light_and_address_objection() -> None:
    outline = make_outline()
    outline.bonuses[0] = make_item(
        "bonus", Format.SHEET, "Planilha bônus", objection_addressed=None
    )
    errors = check_package_rules(outline, make_request())
    assert any("formato liviano" in e for e in errors)
    assert any("objection_addressed" in e for e in errors)


def test_small_items_page_cap() -> None:
    outline = make_outline()
    outline.order_bumps[0].estimated_pages = 20
    assert any("no puede superar" in e for e in check_package_rules(outline, make_request()))


def test_concept_map_relations_reference_existing_ids() -> None:
    content = ConceptMapContent(
        title="t",
        focus_question="q",
        concepts=[Concept(id="a", label="A", description="d")],
        relations=[Relation(source="a", target="zzz", label="causa")],
    )
    assert any("zzz" in e for e in check_content_rules(content))


def sheet(columns: list[Column], rows: list[list[str]]) -> SheetContent:
    tab = SheetTab(
        name="Dívidas",
        kind="tracker",
        instructions="i",
        columns=columns,
        sample_rows=rows,
        empty_rows=10,
    )
    return SheetContent(title="t", purpose="p", how_to_use=["x"], tabs=[tab])


def test_sheet_valid_computation() -> None:
    columns = [
        Column(header="Valor", type="currency", total="sum"),
        Column(header="Juros %", type="percent"),
        Column(
            header="Custo",
            type="currency",
            computed=Computation(op="multiply", operands=["Valor", "Juros %"]),
        ),
    ]
    assert check_content_rules(sheet(columns, [["100", "0.1", ""]])) == []


def test_sheet_unknown_operand_and_bad_row() -> None:
    columns = [
        Column(header="Valor", type="currency"),
        Column(
            header="Custo",
            type="currency",
            computed=Computation(op="multiply", operands=["Valor", "Nope"]),
        ),
    ]
    errors = check_content_rules(sheet(columns, [["100"]]))
    assert any("Nope" in e for e in errors)
    assert any("sample_rows[0]" in e for e in errors)


def test_planner_days_must_match_duration() -> None:
    day = PlannerDay(day=1, focus="f", tasks=["t"], tip="d", reflection_question="r")
    content = PlannerContent(title="t", duration_days=7, introduction="i", days=[day])
    assert check_content_rules(content)


def test_editable_template_needs_matching_body() -> None:
    content = EditableTemplateContent(title="t", instructions=["i"], output="pptx")
    assert check_content_rules(content)
