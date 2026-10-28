"""Hojas imprimibles: sopa de letras correcta, hojas que se dibujan, reglas y paquete."""

import asyncio
import re
from pathlib import Path

import pytest

from app.config import Settings
from app.content.prompts import PromptLibrary
from app.content.rules import check_content_rules, check_package_rules
from app.content.schemas import Format
from app.content.schemas.common import BONUS_FORMATS
from app.content.schemas.formats import PrintableContent, PrintablePage
from app.generators import REGISTRY, RenderContext, generate_files
from app.generators.printable import (
    build_word_search,
    normalize_word,
    prepare,
    render_html,
    shuffled,
    valid_words,
)
from app.generators.samples import PRINTABLE, SAMPLES
from app.templates_engine.model import list_templates, load_template
from tests.fakes import make_outline, make_request

SETTINGS = Settings(_env_file=None)
TEMPLATES = list_templates(SETTINGS.templates_dir)
DEFAULT = load_template(SETTINGS.templates_dir, "minimal-clean")
ROOT = Path(__file__).resolve().parents[2]


def ctx(market: str = "es-LATAM") -> RenderContext:
    return RenderContext(market=market, role="bonus", slug="pack", product_name="Producto")


def page(kind: str, **extra) -> PrintablePage:
    return PrintablePage.model_validate({"kind": kind, "title": f"Hoja {kind}", **extra})


# ───────────────────────────── sopa de letras ─────────────────────────────


def find(grid: list[list[str]], word: str) -> bool:
    size = len(grid)
    for r in range(size):
        for c in range(size):
            for dr, dc in ((0, 1), (1, 0), (1, 1)):
                cells = [(r + dr * i, c + dc * i) for i in range(len(word))]
                if all(
                    y < size and x < size and grid[y][x] == word[i]
                    for i, (y, x) in enumerate(cells)
                ):
                    return True
    return False


WORDS = ["ahorro", "meta", "plan", "deuda", "gasto", "ingreso", "colchón", "presupuesto"]


def test_every_placed_word_is_really_in_the_grid_and_the_rest_is_filler() -> None:
    grid, placed = build_word_search(WORDS, seed=7)
    assert len(placed) == len(WORDS)
    assert all(find(grid, w) for w in placed)
    size = len(grid)
    assert all(len(row) == size for row in grid) and 10 <= size <= 14
    assert all(re.fullmatch(r"[A-Z]", ch) for row in grid for ch in row)


def test_the_same_content_always_gives_the_same_puzzle() -> None:
    assert build_word_search(WORDS, 3) == build_word_search(WORDS, 3)
    assert build_word_search(WORDS, 3)[0] != build_word_search(WORDS, 4)[0]


def test_words_are_normalized_and_bad_ones_dropped() -> None:
    assert normalize_word("Colchón de ahorro!") == "COLCHONDEAHORRO"
    assert valid_words(["Ahorro", "ahorro", "yo", "x" * 13, "Año", "ok ok ok"]) == [
        "AHORRO",
        "ANO",
        "OKOKOK",
    ]
    assert build_word_search([], 1) == ([], [])
    assert build_word_search(["a", "b"], 1) == ([], [])


def test_the_grid_grows_for_a_long_word_and_never_loses_a_placeable_word() -> None:
    grid, placed = build_word_search(["ABCDEFGHIJKL", "ABCDE", "FGHIJ"], 9)
    assert len(grid) >= 12 and "ABCDEFGHIJKL" in placed and all(find(grid, w) for w in placed)


def test_at_most_twelve_words_are_used() -> None:
    many = [f"palabra{chr(97 + i)}" for i in range(20)]
    assert len(valid_words(many)) == 12


# ───────────────────────────── unir y repasar ─────────────────────────────


def test_matching_shuffles_the_right_column_deterministically() -> None:
    values = ["uno", "dos", "tres", "cuatro", "cinco"]
    out = shuffled(values, 11)
    assert sorted(out) == sorted(values) and out != values and out == shuffled(values, 11)
    assert shuffled(["solo"], 1) == ["solo"]
    view = prepare(
        page(
            "matching", items=[{"text": t, "match": m} for t, m in zip("ABCD", "wxyz", strict=True)]
        ),
        {},
        5,
    )
    assert (
        view["left"] == list("ABCD")
        and sorted(view["right"]) == list("wxyz")
        and view["right"] != list("wxyz")
    )


# ───────────────────────────── el PDF ─────────────────────────────


def pdf_text(data: bytes) -> str:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(data)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def test_the_printable_generator_is_registered_and_the_sample_renders_every_sheet() -> None:
    assert Format.PRINTABLE in REGISTRY and SAMPLES[Format.PRINTABLE] is PRINTABLE
    [pdf] = generate_files(Format.PRINTABLE, PRINTABLE, DEFAULT, ctx())
    assert pdf.file_type == "pdf" and pdf.content.startswith(b"%PDF")
    text = pdf_text(pdf.content)
    for expected in (
        "Mis gastos de la semana",
        "Presupuesto del mes",
        "Calendario del mes",
        "Sopa de letras del ahorro",
        "Une cada palabra",
        "Repasa las palabras",
        "Lunes",
        "Ingredientes",
        "Nombre",
        "AHORRO",
    ):
        assert expected in text, expected


@pytest.mark.parametrize("template", [t.id for t in TEMPLATES])
def test_printables_render_on_white_paper_with_any_visual_template(template: str) -> None:
    tpl = load_template(SETTINGS.templates_dir, template)
    html = render_html(PRINTABLE, tpl, ctx())
    assert (
        "background: #fff" in html and "background: var(--bg)" not in html
    )  # papel blanco: ahorra tinta
    [pdf] = generate_files(Format.PRINTABLE, PRINTABLE, tpl, ctx())
    assert pdf.content.startswith(b"%PDF")


def test_the_portuguese_pack_uses_portuguese_labels() -> None:
    html = render_html(PRINTABLE, DEFAULT, ctx("pt-BR"))
    assert (
        "Nome:" in html
        and "Data:" in html
        and "Segunda" in html
        and "Como usar estas folhas" in html
    )


def test_text_from_the_ai_is_escaped() -> None:
    evil = PRINTABLE.model_copy(
        update={
            "title": "<script>alert(1)</script>",
            "pages": [
                page(
                    "checklist",
                    title="<img src=x onerror=alert(1)>",
                    items=[{"text": "<b>x</b>"}] * 4,
                ),
                page("tracker", habits=["<i>h</i>"] * 3, days=7),
                page("table", columns=["<u>a</u>", "b"], rows=5),
                *PRINTABLE.pages[:2],
            ],
        }
    )
    html = render_html(evil, DEFAULT, ctx())
    for tag in ("<script>alert", "<img src=x", "<b>x</b>", "<i>h</i>", "<u>a</u>"):
        assert tag not in html
    assert "&lt;script&gt;" in html


def test_a_big_tracker_keeps_its_circles_inside_their_cells() -> None:
    dot = prepare(page("tracker", habits=["a"] * 3, days=31), {}, 1)["dot"]
    assert 2.2 <= dot <= 2.5
    assert prepare(page("tracker", habits=["a"] * 3, days=7), {}, 1)["dot"] == 4.0


def test_a_sheet_that_overflows_continues_on_the_next_page_without_breaking() -> None:
    long = PRINTABLE.model_copy(
        update={
            "pages": [
                page("worksheet", items=[{"text": f"Pregunta {i}", "lines": 4} for i in range(14)]),
                *PRINTABLE.pages[:3],
            ]
        }
    )
    [pdf] = generate_files(Format.PRINTABLE, long, DEFAULT, ctx())
    assert "Pregunta 13" in pdf_text(pdf.content)


# ───────────────────────────── reglas ─────────────────────────────


def with_pages(*pages: PrintablePage) -> PrintableContent:
    return PRINTABLE.model_copy(update={"pages": list(pages)})


def test_the_sample_passes_the_rules() -> None:
    assert check_content_rules(PRINTABLE) == []


def test_each_kind_must_be_drawable_and_completable() -> None:
    four = [
        page("notes", rows=10),
        page("checklist", items=[{"text": str(i)} for i in range(4)]),
        page("table", columns=["a", "b"], rows=6),
    ]
    ok = with_pages(*four, page("calendar"))
    assert check_content_rules(ok) == []

    def errors(extra: PrintablePage) -> str:
        return " ".join(check_content_rules(with_pages(*four, extra)))

    assert "5 palabras" in errors(page("word_search", items=[{"text": "uno"}, {"text": "dos"}]))
    assert "no repitas" in errors(page("word_search", items=[{"text": "Casa"}] * 6))
    assert "pares" in errors(page("matching", items=[{"text": "a", "match": "b"}] * 2))
    assert "days" in errors(page("tracker", habits=["a", "b", "c"], days=10))
    assert "habits" in errors(page("tracker", habits=["a"], days=7))
    assert "columns" in errors(page("table", columns=["solo"], rows=6))
    assert "rows" in errors(page("table", columns=["a", "b"], rows=2))
    assert "ingredients" in errors(page("recipe", ingredients=["a"], steps=["b"]))
    assert "tracing" in errors(page("tracing", items=[{"text": "palabra-demasiado-larga"}] * 3))
    assert "items" in errors(page("worksheet", items=[{"text": "una"}]))


def test_the_pack_must_be_varied_and_the_right_size() -> None:
    same = [page("notes", rows=10) for _ in range(5)]
    assert "3 tipos" in " ".join(check_content_rules(with_pages(*same)))
    assert "entre 4 y 14" in " ".join(check_content_rules(with_pages(page("notes", rows=10))))
    assert "how_to_use" in " ".join(
        check_content_rules(PRINTABLE.model_copy(update={"how_to_use": ["uno"]}))
    )


# ───────────────────────────── paquete, prompts y espejos ─────────────────────────────


def test_a_printable_bonus_is_accepted_by_the_package_rules() -> None:
    assert Format.PRINTABLE in BONUS_FORMATS
    outline = make_outline()
    bonuses = [
        outline.bonuses[0].model_copy(update={"format": Format.PRINTABLE}),
        *outline.bonuses[1:],
    ]
    outline = outline.model_copy(update={"bonuses": bonuses})
    assert not [
        e
        for e in check_package_rules(outline, make_request())
        if "printable" in e or "liviano" in e
    ]


def test_the_ai_is_taught_when_to_add_printables_in_both_markets() -> None:
    library = PromptLibrary(SETTINGS.prompts_dir)
    for market in ("es-LATAM", "pt-BR"):
        guide = library.format_guide(market, Format.PRINTABLE)
        for kind in (
            "worksheet",
            "table",
            "tracker",
            "calendar",
            "recipe",
            "word_search",
            "matching",
            "tracing",
        ):
            assert kind in guide, (market, kind)
        outline = (SETTINGS.prompts_dir / market / "outline.md").read_text(encoding="utf-8")
        assert "printable" in outline


def test_the_frontend_and_the_database_know_the_new_format() -> None:
    types = (ROOT / "frontend" / "lib" / "types.ts").read_text(encoding="utf-8")
    declared = re.findall(
        r'"([a-z_]+)"', re.search(r"FORMATS = \[(.*?)\] as const", types, re.S).group(1)
    )
    assert declared == [f.value for f in Format]  # mismo orden y mismos valores que el backend
    assert '"printable"' in (ROOT / "frontend" / "lib" / "remodel.ts").read_text(encoding="utf-8")
    for lang in ("es", "pt"):
        assert '"printable"' in (ROOT / "frontend" / "messages" / f"{lang}.json").read_text(
            encoding="utf-8"
        )
    migrations = "".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "supabase" / "migrations").glob("*.sql")
    )
    assert "add value if not exists 'printable'" in migrations


def test_a_package_with_a_printable_piece_generates_its_pdf() -> None:
    from app.pipeline.generate import run_generate
    from tests.test_engines import commercial
    from tests.test_pipeline import item_responses, setup

    outline = make_outline()
    bonuses = [
        outline.bonuses[0].model_copy(update={"format": Format.PRINTABLE}),
        *outline.bonuses[1:],
    ]
    outline = outline.model_copy(update={"bonuses": bonuses})
    deps, product, job, _ = setup([*item_responses(outline), commercial("BRL")])
    product["outline"] = outline.model_dump(mode="json")
    asyncio.run(run_generate(job, deps))

    assert product["status"] == "ready"
    printable = next(i for i in deps.items.rows.values() if i["format"] == "printable")
    files = [f for f in deps.files.rows.values() if f["product_item_id"] == printable["id"]]
    assert [f["file_type"] for f in files] == ["pdf"]
    assert printable["content"]["pages"] and printable["status"] == "ready"


def test_ai_schema_marks_every_printable_field_required():
    # La API rechaza ("Schema is too complex") los esquemas con muchos campos opcionales.
    from app.content.schemas.formats import PrintableContent

    schema = PrintableContent.model_json_schema()
    for name in ("PrintableContent", "PrintablePage", "PrintableItem"):
        node = schema if name == "PrintableContent" else schema["$defs"][name]
        assert set(node["required"]) == set(node["properties"])
        assert all("default" not in p for p in node["properties"].values())
