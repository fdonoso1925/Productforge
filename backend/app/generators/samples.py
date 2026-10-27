"""Contenido de ejemplo por formato: para miniaturas de plantillas y tests de generadores."""

from app.content.schemas import Format
from app.content.schemas.formats import (
    BlueprintContent,
    ChecklistContent,
    ConceptMapContent,
    EditableTemplateContent,
    GuideContent,
    MindMapContent,
    PlannerContent,
    PrintableContent,
    SheetContent,
    SwipeFileContent,
)

GUIDE = GuideContent.model_validate(
    {
        "title": "Adiós Sobregiro",
        "subtitle": "El plan de 60 días para salir del rojo ganando el sueldo mínimo",
        "promise": "Cuenta en cero y un colchón de USD 100 en 60 días",
        "introduction": [
            "Si cada mes el sueldo llega y desaparece en intereses, no es falta de disciplina: "
            "es una trampa con reglas que casi nadie explica.",
            "Esta guía te muestra, paso a paso, cómo cortar el interés hoy y salir del rojo.",
        ],
        "chapters": [
            {
                "title": "El diagnóstico de 15 minutos",
                "summary": "Antes de cortar gastos, mide cuánto te cuesta el sobregiro de verdad.",
                "sections": [
                    {
                        "heading": "Junta tus números",
                        "paragraphs": ["Abre la app del banco y anota tres cifras del último mes."],
                        "steps": [
                            "Anota el saldo más negativo del mes.",
                            "Suma los intereses y comisiones cobrados.",
                            "Calcula cuántos días estuviste en rojo.",
                        ],
                        "example": "Ana gana USD 420 y pagó USD 38 de interés en 22 días en rojo.",
                        "callouts": [
                            {
                                "kind": "tip",
                                "title": "Usa la planilla",
                                "text": "La Planilla Salida del Rojo hace estos cálculos por ti.",
                            },
                            {
                                "kind": "warning",
                                "title": "",
                                "text": "No abras otro crédito para tapar este sin comparar tasas.",
                            },
                        ],
                    }
                ],
            },
            {
                "title": "Corta el interés esta semana",
                "summary": "La deuda más cara se ataca primero.",
                "sections": [
                    {
                        "heading": "Negocia con el banco",
                        "paragraphs": [
                            "Pide convertir el sobregiro en un préstamo en cuotas con tasa menor."
                        ],
                        "bullets": ["Llama un martes temprano.", "Pide la tasa por escrito."],
                        "callouts": [
                            {
                                "kind": "exercise",
                                "title": "Tu guion",
                                "text": "Escribe en una línea cuánto puedes pagar por mes.",
                            }
                        ],
                    }
                ],
            },
        ],
        "conclusion": ["Salir del rojo es un proceso de semanas, no de meses de sufrimiento."],
        "next_steps": ["Haz el diagnóstico hoy.", "Llama al banco esta semana."],
    }
)

CHECKLIST = ChecklistContent.model_validate(
    {
        "title": "Checklist de Negociación",
        "introduction": "Marca cada paso antes de llamar al banco.",
        "groups": [
            {
                "title": "Antes de llamar",
                "items": [
                    {"text": "Tener a mano el saldo y los intereses del mes"},
                    {
                        "text": "Definir la cuota máxima que puedes pagar",
                        "detail": "Máximo 20 % del sueldo.",
                    },
                ],
            },
            {"title": "Durante la llamada", "items": [{"text": "Pedir la tasa por escrito"}]},
        ],
        "writing_prompts": [{"question": "¿Qué cuota mensual puedes sostener?", "lines": 3}],
    }
)

BLUEPRINT = BlueprintContent.model_validate(
    {
        "title": "Blueprint 60 Días",
        "overview": "Tres fases para pasar del rojo a un colchón propio.",
        "phases": [
            {
                "name": "Frenar",
                "duration": "Semana 1",
                "objective": "Cortar el interés",
                "steps": ["Diagnóstico", "Negociación"],
                "deliverables": ["Tasa nueva por escrito"],
                "common_mistakes": ["Abrir otro crédito caro"],
            },
            {
                "name": "Salir",
                "duration": "Semanas 2 a 6",
                "objective": "Saldo en cero",
                "steps": ["Pago semanal fijo"],
                "deliverables": ["Cuenta en cero"],
                "common_mistakes": ["Pagar sin registrar"],
            },
        ],
        "success_metrics": ["Cero días en rojo durante 30 días seguidos"],
    }
)

PLANNER = PlannerContent.model_validate(
    {
        "title": "Planner 7 Días",
        "duration_days": 7,
        "introduction": "Una tarea pequeña por día.",
        "days": [
            {
                "day": d,
                "focus": f"Foco del día {d}",
                "tasks": ["Revisar saldo", "Anotar gastos"],
                "tip": "Hazlo a la misma hora.",
                "reflection_question": "¿Qué gasto evitaste hoy?",
            }
            for d in range(1, 8)
        ],
        "weekly_review_questions": ["¿Cuántos días estuviste en rojo?"],
    }
)

SWIPE = SwipeFileContent.model_validate(
    {
        "title": "Banco de Mensajes al Banco",
        "introduction": "Copia, pega y ajusta los datos entre corchetes.",
        "categories": [
            {
                "name": "Pedir renegociación",
                "when_to_use": "Cuando llevas más de 10 días en rojo.",
                "entries": [
                    {
                        "label": "Mensaje por app",
                        "text": "Hola, soy [NOMBRE], cliente hace [AÑOS] años. Quiero convertir mi "
                        "sobregiro en cuotas de hasta [MONTO].",
                        "notes": "Envíalo por el chat oficial para que quede registro.",
                    }
                ],
            },
        ],
    }
)

MIND_MAP = MindMapContent.model_validate(
    {
        "title": "Mapa de la Salida del Rojo",
        "central_idea": "Cuenta en cero en 60 días",
        "branches": [
            {"label": "Diagnóstico", "children": [{"label": "Saldo"}, {"label": "Intereses"}]},
            {
                "label": "Negociación",
                "note": "Semana 1",
                "children": [
                    {"label": "Guion", "children": ["Tasa", "Cuota"]},
                    {"label": "Registro"},
                ],
            },
            {"label": "Pagos", "children": [{"label": "Semanal"}, {"label": "Automático"}]},
            {"label": "Colchón", "children": [{"label": "USD 100"}]},
        ],
    }
)

CONCEPT_MAP = ConceptMapContent.model_validate(
    {
        "title": "Cómo funciona el sobregiro",
        "focus_question": "¿Por qué el sobregiro se come el sueldo?",
        "concepts": [
            {"id": "sobregiro", "label": "Sobregiro", "description": "Crédito automático"},
            {"id": "interes", "label": "Interés diario", "description": "Se cobra por día"},
            {"id": "sueldo", "label": "Sueldo", "description": "Entra a fin de mes"},
            {"id": "cuotas", "label": "Préstamo en cuotas", "description": "Tasa menor"},
        ],
        "relations": [
            {"source": "sobregiro", "target": "interes", "label": "genera"},
            {"source": "interes", "target": "sueldo", "label": "consume"},
            {"source": "cuotas", "target": "sobregiro", "label": "reemplaza"},
        ],
    }
)

SHEET = SheetContent.model_validate(
    {
        "title": "Planilla Salida del Rojo",
        "purpose": "Calcular cuánto te cuesta el sobregiro y seguir los pagos.",
        "how_to_use": ["Completa una fila por deuda.", "Las columnas grises se calculan solas."],
        "tabs": [
            {
                "name": "Deudas",
                "kind": "calculator",
                "instructions": "Una fila por cada deuda.",
                "columns": [
                    {"header": "Deuda", "type": "text"},
                    {"header": "Saldo", "type": "currency", "total": "sum"},
                    {"header": "Interés mensual", "type": "percent"},
                    {
                        "header": "Costo mensual",
                        "type": "currency",
                        "total": "sum",
                        "computed": {"op": "multiply", "operands": ["Saldo", "Interés mensual"]},
                    },
                    {"header": "Prioridad", "type": "choice", "choices": ["Alta", "Media", "Baja"]},
                    {"header": "Pagada", "type": "checkbox"},
                ],
                "sample_rows": [
                    ["Sobregiro", "350", "8%", "", "Alta", "No"],
                    ["Tarjeta", "120,50", "6.5%", "", "Media", "No"],
                ],
                "empty_rows": 10,
            },
            {
                "name": "Pagos",
                "kind": "tracker",
                "instructions": "Registra cada pago.",
                "columns": [
                    {"header": "Fecha", "type": "date"},
                    {"header": "Monto", "type": "currency", "total": "sum"},
                    {"header": "Saldo antes", "type": "currency"},
                    {
                        "header": "Saldo después",
                        "type": "currency",
                        "computed": {"op": "subtract", "operands": ["Saldo antes", "Monto"]},
                    },
                ],
                "sample_rows": [["2026-10-01", "50", "350", ""]],
                "empty_rows": 30,
            },
        ],
    }
)

TEMPLATE_DOCX = EditableTemplateContent.model_validate(
    {
        "title": "Guiones para el Banco",
        "instructions": ["Reemplaza lo que está entre [CORCHETES]."],
        "output": "docx",
        "documents": [
            {
                "name": "Carta de renegociación",
                "purpose": "Pedir cuotas por escrito.",
                "blocks": [
                    {"kind": "heading", "text": "Solicitud de renegociación"},
                    {
                        "kind": "paragraph",
                        "text": "Estimados, por medio de la presente solicito...",
                    },
                    {"kind": "placeholder", "text": "[NOMBRE COMPLETO] - [RUT/DNI]"},
                    {
                        "kind": "bullets",
                        "text": "Condiciones",
                        "items": ["Cuota: [MONTO]", "Plazo: [MESES]"],
                    },
                ],
            },
        ],
    }
)

TEMPLATE_PPTX = EditableTemplateContent.model_validate(
    {
        "title": "Presentación del Plan",
        "instructions": ["Edita cada diapositiva."],
        "output": "pptx",
        "slides": [
            {
                "title": "Mi plan de 60 días",
                "bullets": ["Frenar", "Salir", "Ahorrar"],
                "speaker_notes": "Presenta el plan en 1 minuto.",
            },
            {"title": "Semana 1", "bullets": ["Diagnóstico", "Llamada al banco"]},
        ],
    }
)

PRINTABLE = PrintableContent.model_validate(
    {
        "title": "Pack imprimible: Orden y Ahorro en Casa",
        "audience_note": "Para la familia: los niños pueden hacerlas con una persona adulta.",
        "how_to_use": [
            "Imprime en A4; en blanco y negro está bien.",
            "Usa lápiz para poder repetir cada hoja las veces que quieras.",
            "Pega el calendario y el seguimiento a la vista.",
        ],
        "pages": [
            {
                "kind": "worksheet",
                "title": "Mis gastos de la semana",
                "instructions": "Responde cada pregunta con tus propias palabras.",
                "items": [
                    {"text": "¿En qué gasté más esta semana?", "lines": 2},
                    {"text": "¿Qué gasto pude evitar?", "lines": 2, "hint": "Piensa en lo pequeño"},
                    {"text": "¿Qué voy a cambiar la próxima semana?", "lines": 3},
                ],
                "footer": "Cada decisión pequeña suma.",
            },
            {
                "kind": "table",
                "title": "Presupuesto del mes",
                "instructions": "Anota lo que planeas y lo que realmente gastaste.",
                "columns": ["Categoría", "Planeado", "Real", "Diferencia"],
                "rows": 10,
            },
            {
                "kind": "tracker",
                "title": "Seguimiento de hábitos de ahorro",
                "instructions": "Pinta un círculo cada día que lo cumplas.",
                "habits": [
                    "Anoté mis gastos",
                    "No compré por impulso",
                    "Revisé mi saldo",
                    "Aparté mi ahorro",
                ],
                "days": 30,
            },
            {
                "kind": "calendar",
                "title": "Calendario del mes",
                "calendar_kind": "month",
                "instructions": "Escribe las fechas y marca los pagos.",
            },
            {"kind": "calendar", "title": "Plan de la semana", "calendar_kind": "week"},
            {
                "kind": "recipe",
                "title": "Receta económica: arroz con verduras",
                "servings": "4 porciones",
                "time": "30 minutos",
                "ingredients": ["1 taza de arroz", "1 zanahoria", "1 cebolla", "Sal y aceite"],
                "steps": [
                    "Lava y corta las verduras.",
                    "Sofríe la cebolla y la zanahoria.",
                    "Agrega el arroz y el agua.",
                    "Cocina tapado 20 minutos.",
                ],
            },
            {
                "kind": "word_search",
                "title": "Sopa de letras del ahorro",
                "instructions": "Encuentra las palabras en horizontal, vertical y diagonal.",
                "items": [
                    {"text": t}
                    for t in ["ahorro", "meta", "plan", "deuda", "gasto", "ingreso", "colchón"]
                ],
            },
            {
                "kind": "matching",
                "title": "Une cada palabra con su significado",
                "items": [
                    {"text": "Ahorro", "match": "Guardar para después"},
                    {"text": "Gasto", "match": "Dinero que sale"},
                    {"text": "Ingreso", "match": "Dinero que entra"},
                    {"text": "Meta", "match": "Lo que quiero lograr"},
                ],
            },
            {
                "kind": "tracing",
                "title": "Repasa las palabras",
                "items": [{"text": "ahorro"}, {"text": "meta"}, {"text": "plan"}],
            },
            {
                "kind": "checklist",
                "title": "Lista de compras inteligente",
                "items": [
                    {"text": "Revisar lo que ya tengo"},
                    {"text": "Anotar solo lo necesario"},
                    {"text": "Comparar precios"},
                    {"text": "Llevar el monto exacto"},
                ],
            },
            {"kind": "notes", "title": "Mis ideas para ahorrar", "rows": 14},
        ],
    }
)

SAMPLES = {
    Format.PDF_GUIDE: GUIDE,
    Format.EPUB: GUIDE,
    Format.CHECKLIST: CHECKLIST,
    Format.BLUEPRINT: BLUEPRINT,
    Format.PLANNER: PLANNER,
    Format.SWIPE_FILE: SWIPE,
    Format.PRINTABLE: PRINTABLE,
    Format.MIND_MAP: MIND_MAP,
    Format.CONCEPT_MAP: CONCEPT_MAP,
    Format.SHEET: SHEET,
    Format.EDITABLE_TEMPLATE: TEMPLATE_DOCX,
}


# Los formatos con infografías usan sus versiones «ricas» (guía, blueprint, checklist, planner).
from app.generators import samples_visuals  # noqa: E402,F401  (reemplaza entradas de SAMPLES)
