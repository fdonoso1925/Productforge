"""Ejemplos de infografías para pruebas y vistas previas: un visual de cada tipo y las versiones
«ricas» de los formatos que los llevan (guía, blueprint, checklist, planner)."""

from app.content.schemas.formats import PhotoSpec, Visual
from app.generators.samples import BLUEPRINT, CHECKLIST, GUIDE, PLANNER


def visual(kind: str, title: str, items: list[dict], **extra) -> Visual:
    return Visual.model_validate({"kind": kind, "title": title, "items": items, **extra})


PROCESS = visual(
    "process",
    "Tu ruta de salida en 4 pasos",
    [
        {
            "label": "Mide tu deuda",
            "detail": "Junta saldo, tasa y pagos mínimos de cada tarjeta.",
            "icon": "chart",
        },
        {
            "label": "Negocia la tasa",
            "detail": "Llama al banco con el guion y pide por escrito.",
            "icon": "user",
        },
        {
            "label": "Ordena los pagos",
            "detail": "Primero la más cara, el mínimo en las demás.",
            "icon": "target",
        },
        {
            "label": "Cierra el ciclo",
            "detail": "Revisa cada semana y celebra cada tarjeta en cero.",
            "icon": "flag",
        },
    ],
    caption="Cada paso se apoya en el anterior: no te saltes el diagnóstico.",
)
PROCESS_SIX = visual(
    "process",
    "Del caos al sistema en seis pasos",
    [
        {"label": f"Paso {i}: {t}", "detail": "Una frase corta que lo explica bien."}
        for i, t in enumerate(
            ["inventario", "prioridades", "calendario", "ejecución", "revisión", "mejora"], start=1
        )
    ],
)
TIMELINE = visual(
    "timeline",
    "Línea de tiempo de los 60 días",
    [
        {"label": "Día 1", "detail": "Diagnóstico de 15 minutos"},
        {"label": "Semana 1", "detail": "Negociación de tasas"},
        {"label": "Semana 3", "detail": "Primer saldo en cero"},
        {"label": "Semana 6", "detail": "Colchón inicial"},
        {"label": "Día 60", "detail": "Revisión y siguiente meta"},
    ],
)
CYCLE = visual(
    "cycle",
    "El ciclo semanal del dinero",
    [
        {"label": "Registrar", "detail": "Anota cada gasto el mismo día"},
        {"label": "Revisar", "detail": "Domingo: 10 minutos con tus números"},
        {"label": "Ajustar", "detail": "Mueve una categoría, no todas"},
        {"label": "Pagar", "detail": "Transferencia automática a la deuda"},
    ],
)
PYRAMID = visual(
    "pyramid",
    "Pirámide de prioridades",
    [
        {"label": "Colchón de emergencia", "detail": "Tu meta final tras salir del rojo"},
        {"label": "Deudas caras", "detail": "Las de interés más alto, primero"},
        {"label": "Gastos esenciales", "detail": "Vivienda, comida, transporte"},
    ],
)
FUNNEL = visual(
    "funnel",
    "Embudo de decisiones de compra",
    [
        {"label": "Necesidad real", "detail": "¿Lo necesito o lo quiero?"},
        {"label": "Alternativas", "detail": "¿Hay una opción más barata?"},
        {"label": "Espera 48 horas", "detail": "Si sigue en pie, decide"},
    ],
)
MATRIX = visual(
    "matrix",
    "Qué recortar primero",
    [
        {"label": "Quick wins", "detail": "Bajo esfuerzo, alto impacto"},
        {"label": "Grandes proyectos", "detail": "Alto esfuerzo, alto impacto"},
        {"label": "Relleno", "detail": "Bajo esfuerzo, bajo impacto"},
        {"label": "Evitar", "detail": "Alto esfuerzo, bajo impacto"},
    ],
    axis_x="Esfuerzo",
    axis_y="Impacto",
)
COMPARISON = visual(
    "comparison",
    "Pagar el mínimo vs. pagar con un plan",
    [
        {"label": "Los intereses crecen cada mes"},
        {"label": "No sabes cuándo terminas"},
        {"label": "Pagas por la deuda, no por tu futuro"},
    ],
    right_items=[
        {"label": "El interés baja con cada pago"},
        {"label": "Fecha de salida calculada"},
        {"label": "Cada pago te acerca a tu colchón"},
    ],
    left_title="Pagar el mínimo",
    right_title="Pagar con plan",
)
CARDS = visual(
    "cards",
    "Las 4 ideas que sostienen el método",
    [
        {"label": "Claridad", "detail": "Sin números no hay decisiones.", "icon": "bulb"},
        {"label": "Prioridad", "detail": "Una deuda a la vez.", "icon": "target"},
        {
            "label": "Constancia",
            "detail": "Pequeño y semanal gana a grande y raro.",
            "icon": "clock",
        },
        {"label": "Protección", "detail": "Un colchón evita volver al rojo.", "icon": "heart"},
    ],
)
CHECKLIST_V = visual(
    "checklist",
    "Antes de llamar al banco",
    [
        {"label": "Tengo el saldo y la tasa de cada tarjeta"},
        {"label": "Sé cuánto puedo pagar al mes", "detail": "Después de gastos esenciales"},
        {"label": "Tengo el guion a mano"},
    ],
)
BARS = visual(
    "bars",
    "Reparto sugerido del sueldo",
    [
        {"label": "Necesidades", "value": 50},
        {"label": "Deudas y ahorro", "value": 30},
        {"label": "Gustos", "value": 20},
    ],
    unit=" %",
)
DONUT = visual(
    "donut",
    "Cómo repartir cada pago extra",
    [
        {"label": "Deuda más cara", "value": 60},
        {"label": "Colchón", "value": 30},
        {"label": "Un gusto", "value": 10},
    ],
    unit=" %",
)

ALL = {
    "process": PROCESS,
    "process_six": PROCESS_SIX,
    "timeline": TIMELINE,
    "cycle": CYCLE,
    "pyramid": PYRAMID,
    "funnel": FUNNEL,
    "matrix": MATRIX,
    "comparison": COMPARISON,
    "cards": CARDS,
    "checklist": CHECKLIST_V,
    "bars": BARS,
    "donut": DONUT,
}


def rich_guide():
    pool = [PROCESS, COMPARISON, TIMELINE, CYCLE, PYRAMID, MATRIX]
    chapters = []
    for i, chapter in enumerate(GUIDE.chapters):
        sections = list(chapter.sections)
        sections[0] = sections[0].model_copy(update={"visual": pool[i % len(pool)]})
        update: dict = {"sections": sections}
        if i == 0:
            update["photo"] = PhotoSpec(
                scene="calculator and notebook on a desk",
                keywords=["budget", "desk"],
                caption="Empieza por los números",
            )
        chapters.append(chapter.model_copy(update=update))
    return GUIDE.model_copy(update={"overview": CARDS, "chapters": chapters})


def rich_blueprint():
    phases = [
        BLUEPRINT.phases[0].model_copy(update={"flow": PROCESS}),
        BLUEPRINT.phases[1].model_copy(update={"flow": CYCLE}),
    ]
    return BLUEPRINT.model_copy(
        update={"roadmap": TIMELINE, "phases": phases, "success_visual": CARDS}
    )


def rich_checklist():
    return CHECKLIST.model_copy(update={"visual": PROCESS})


def rich_planner():
    return PLANNER.model_copy(update={"roadmap": TIMELINE})


def _install() -> None:
    from app.content.schemas import Format
    from app.generators import samples

    samples.SAMPLES[Format.PDF_GUIDE] = rich_guide()
    samples.SAMPLES[Format.EPUB] = rich_guide()
    samples.SAMPLES[Format.BLUEPRINT] = rich_blueprint()
    samples.SAMPLES[Format.CHECKLIST] = rich_checklist()
    samples.SAMPLES[Format.PLANNER] = rich_planner()


_install()
