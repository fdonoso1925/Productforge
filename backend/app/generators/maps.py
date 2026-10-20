"""Mapas mentales y conceptuales (D7: render SVG propio en Python, sin Chromium).

Salidas: SVG, PDF (SVG maquetado con la plantilla) y PNG (rasterizado del PDF), más
versiones editables: Markmap (.md), Mermaid (.mmd), OPML, FreeMind (.mm) y XMind para
el mapa mental; Mermaid y draw.io para el conceptual (grafos con relaciones).
"""

import base64
import io
import json
import textwrap
import uuid
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import ClassVar
from xml.sax.saxutils import escape, quoteattr

from app.content.schemas import Format
from app.content.schemas.formats import ConceptMapContent, MindMapContent
from app.generators.base import FileArtifact, RenderContext, artifact, register
from app.generators.render import html_to_pdf, pdf_page_to_png
from app.templates_engine.model import Template

CHAR_W = 7.6  # ancho aproximado por carácter a 14px


def wrap(text: str, width: int = 22) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=True) or [""]


def text_block(lines: list[str], x: float, y: float, size: int, anchor: str, **attrs) -> str:
    extra = " ".join(f"{k.replace('_', '-')}={quoteattr(str(v))}" for k, v in attrs.items())
    top = y - (len(lines) - 1) * size * 0.6
    spans = "".join(
        f'<tspan x="{x:.1f}" y="{top + i * size * 1.2:.1f}">{escape(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return (
        f'<text text-anchor="{anchor}" dominant-baseline="middle" font-size="{size}" {extra}>'
        f"{spans}</text>"
    )


def svg_document(
    width: float, height: float, body: str, template: Template, x0: float = 0, y0: float = 0
) -> str:
    p = template.palette
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {width:.0f} '
        f'{height:.0f}" width="{width:.0f}" height="{height:.0f}" '
        f"font-family={quoteattr(template.fonts.body.family + ', sans-serif')}>"
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{width:.0f}" height="{height:.0f}" '
        f'fill="{p.background}"/>{body}</svg>'
    )


class Bounds:
    """Caja que envuelve todo lo dibujado, para recortar el viewBox al contenido."""

    def __init__(self) -> None:
        self.x0 = self.y0 = float("inf")
        self.x1 = self.y1 = float("-inf")

    def add(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.x1 = min(self.x0, x0, x1), max(self.x1, x0, x1)
        self.y0, self.y1 = min(self.y0, y0, y1), max(self.y1, y0, y1)

    def document(self, body: str, template: Template, margin: float = 40) -> str:
        return svg_document(
            self.x1 - self.x0 + 2 * margin,
            self.y1 - self.y0 + 2 * margin,
            body,
            template,
            self.x0 - margin,
            self.y0 - margin,
        )


def branch_colors(template: Template) -> list[str]:
    p = template.palette
    return [p.primary, p.secondary, p.accent, p.tip, p.warning, p.exercise]


# ─────────────────────────── Mapa mental ───────────────────────────


@dataclass
class Node:
    label: str
    children: list["Node"] = field(default_factory=list)
    note: str | None = None
    x: float = 0
    y: float = 0


def mind_tree(content: MindMapContent) -> Node:
    return Node(
        content.central_idea,
        [
            Node(
                b.label,
                [Node(leaf.label, [Node(g) for g in leaf.children]) for leaf in b.children],
                note=b.note,
            )
            for b in content.branches
        ],
    )


def leaves(node: Node) -> int:
    return max(1, sum(leaves(c) for c in node.children))


def mind_map_svg(content: MindMapContent, template: Template) -> str:
    root = mind_tree(content)
    right = root.children[0::2]
    left = root.children[1::2]
    row_h, offsets = 38, (0, 270, 520, 740)
    height = max(sum(leaves(b) for b in right), sum(leaves(b) for b in left), 6) * row_h + 120
    width = 1600
    cx, cy = width / 2, height / 2
    colors = branch_colors(template)
    p = template.palette
    edges: list[str] = []
    nodes: list[str] = []
    bounds = Bounds()

    def place(node: Node, depth: int, side: int, top: float) -> float:
        node.x = cx + side * offsets[depth]
        if node.children:
            cursor = top
            ys = []
            for child in node.children:
                ys.append(place(child, depth + 1, side, cursor))
                cursor += leaves(child) * row_h
            node.y = sum(ys) / len(ys)
        else:
            node.y = top + row_h / 2
        return node.y

    for side, group in ((1, right), (-1, left)):
        total = sum(leaves(b) for b in group) * row_h
        cursor = cy - total / 2
        for branch in group:
            place(branch, 1, side, cursor)
            cursor += leaves(branch) * row_h

    def draw(node: Node, depth: int, side: int, color: str, parent: Node) -> None:
        x0 = parent.x + side * (110 if depth == 1 else 8)
        mid = (x0 + node.x) / 2
        edges.append(
            f'<path d="M{x0:.1f},{parent.y:.1f} C{mid:.1f},{parent.y:.1f} {mid:.1f},{node.y:.1f} '
            f'{node.x:.1f},{node.y:.1f}" stroke="{color}" stroke-width="{max(1.5, 5 - depth)}" '
            f'fill="none" stroke-linecap="round"/>'
        )
        anchor = "start" if side > 0 else "end"
        if depth == 1:
            lines = wrap(node.label, 20)
            w = max(len(line) for line in lines) * CHAR_W * 1.15 + 28
            h = len(lines) * 19 + 16
            bx = node.x if side > 0 else node.x - w
            nodes.append(
                f'<rect x="{bx:.1f}" y="{node.y - h / 2:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="10" fill="{p.background}" stroke="{color}" stroke-width="2.5"/>'
            )
            nodes.append(
                text_block(lines, bx + w / 2, node.y, 15, "middle", fill=p.text, font_weight="700")
            )
            if node.note:
                ny = node.y + h / 2 + 12
                nodes.append(text_block([node.note], bx + w / 2, ny, 11, "middle", fill=p.muted))
            bounds.add(bx, node.y - h / 2, bx + w, node.y + h / 2 + (20 if node.note else 0))
            child_origin = Node(node.label, x=node.x + side * w, y=node.y)
        else:
            lines = wrap(node.label, 26)
            tx = node.x + side * 6
            nodes.append(
                text_block(
                    lines,
                    tx,
                    node.y,
                    13 if depth == 2 else 12,
                    anchor,
                    fill=p.text if depth == 2 else p.muted,
                )
            )
            width_px = max(len(line) for line in lines) * CHAR_W
            half = len(lines) * 9
            bounds.add(tx, node.y - half, tx + side * width_px, node.y + half)
            child_origin = Node(node.label, x=node.x + side * (width_px + 10), y=node.y)
        for child in node.children:
            draw(child, depth + 1, side, color, child_origin)

    center_lines = wrap(root.label, 18)
    cw = max(len(line) for line in center_lines) * CHAR_W * 1.3 + 44
    ch = len(center_lines) * 22 + 30
    root.x, root.y = cx, cy
    for i, branch in enumerate(root.children):
        side = 1 if branch in right else -1
        origin = Node(root.label, x=cx + side * (cw / 2 - 110), y=cy)
        draw(branch, 1, side, colors[i % len(colors)], origin)
    nodes.append(
        f'<rect x="{cx - cw / 2:.1f}" y="{cy - ch / 2:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
        f'rx="{ch / 2:.1f}" fill="{p.primary}"/>'
    )
    nodes.append(
        text_block(center_lines, cx, cy, 18, "middle", fill=p.on_primary, font_weight="700")
    )
    bounds.add(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    return bounds.document("".join(edges) + "".join(nodes), template)


def mind_map_markmap(content: MindMapContent) -> str:
    out = [f"# {content.central_idea}", ""]
    for b in content.branches:
        out.append(f"## {b.label}")
        for leaf in b.children:
            out.append(f"- {leaf.label}")
            out += [f"  - {g}" for g in leaf.children]
        out.append("")
    return "\n".join(out)


def mermaid_text(text: str) -> str:
    return "".join(" " if ch in '()[]{}<>"`' else ch for ch in text).strip() or "-"


def mind_map_mermaid(content: MindMapContent) -> str:
    out = ["mindmap", f"  root(({mermaid_text(content.central_idea)}))"]
    for b in content.branches:
        out.append(f"    {mermaid_text(b.label)}")
        for leaf in b.children:
            out.append(f"      {mermaid_text(leaf.label)}")
            out += [f"        {mermaid_text(g)}" for g in leaf.children]
    return "\n".join(out) + "\n"


def mind_map_opml(content: MindMapContent) -> str:
    def outline(text: str, inner: str = "", note: str | None = None) -> str:
        note_attr = f" _note={quoteattr(note)}" if note else ""
        return f"<outline text={quoteattr(text)}{note_attr}>{inner}</outline>"

    body = outline(
        content.central_idea,
        "".join(
            outline(
                b.label,
                "".join(
                    outline(leaf.label, "".join(outline(g) for g in leaf.children))
                    for leaf in b.children
                ),
                b.note,
            )
            for b in content.branches
        ),
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0"><head>'
        f"<title>{escape(content.title)}</title></head><body>{body}</body></opml>\n"
    )


def mind_map_freemind(content: MindMapContent) -> str:
    def node(text: str, inner: str = "", position: str = "") -> str:
        pos = f' POSITION="{position}"' if position else ""
        return f"<node TEXT={quoteattr(text)}{pos}>{inner}</node>"

    branches = "".join(
        node(
            b.label,
            "".join(
                node(leaf.label, "".join(node(g) for g in leaf.children)) for leaf in b.children
            ),
            "right" if i % 2 == 0 else "left",
        )
        for i, b in enumerate(content.branches)
    )
    return f'<map version="1.0.1">{node(content.central_idea, branches)}</map>\n'


def mind_map_xmind(content: MindMapContent) -> bytes:
    def topic(title: str, children: list[dict] | None = None, note: str | None = None) -> dict:
        data: dict = {"id": uuid.uuid4().hex, "class": "topic", "title": title}
        if children:
            data["children"] = {"attached": children}
        if note:
            data["notes"] = {"plain": {"content": note}}
        return data

    root = topic(
        content.central_idea,
        [
            topic(
                b.label,
                [topic(leaf.label, [topic(g) for g in leaf.children]) for leaf in b.children],
                b.note,
            )
            for b in content.branches
        ],
    )
    root["structureClass"] = "org.xmind.ui.map.unbalanced"
    sheet = [{"id": uuid.uuid4().hex, "class": "sheet", "title": content.title, "rootTopic": root}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(sheet, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps({"creator": {"name": "ProductForge"}}))
        z.writestr(
            "manifest.json", json.dumps({"file-entries": {"content.json": {}, "metadata.json": {}}})
        )
    return buffer.getvalue()


# ─────────────────────────── Mapa conceptual ───────────────────────────

NODE_W, COL_W, ROW_GAP = 210, 310, 120


def concept_layout(content: ConceptMapContent) -> dict[str, tuple[float, float, list[str]]]:
    """Columnas por BFS desde los conceptos sin entradas (izquierda → derecha, para la
    página apaisada); devuelve id → (x, y, líneas)."""
    ids = [c.id for c in content.concepts]
    incoming = {r.target for r in content.relations if r.source != r.target}
    out_edges = defaultdict(list)
    for r in content.relations:
        out_edges[r.source].append(r.target)
    roots = [i for i in ids if i not in incoming] or ids[:1]
    layer: dict[str, int] = {}
    queue = deque((r, 0) for r in roots)
    while queue:
        node, depth = queue.popleft()
        if node in layer:
            continue
        layer[node] = depth
        queue.extend((t, depth + 1) for t in out_edges[node] if t not in layer)
    for i in ids:
        layer.setdefault(i, 0)
    columns = defaultdict(list)
    for i in ids:
        columns[layer[i]].append(i)
    height = max(len(c) for c in columns.values()) * ROW_GAP
    labels = {c.id: c.label for c in content.concepts}
    positions = {}
    for depth, members in columns.items():
        gap = height / len(members)
        for k, node_id in enumerate(members):
            y = gap * (k + 0.5)
            positions[node_id] = (NODE_W / 2 + depth * COL_W, y, wrap(labels[node_id], 24))
    return positions


def concept_map_svg(content: ConceptMapContent, template: Template) -> str:
    pos = concept_layout(content)
    p = template.palette
    bounds = Bounds()
    marker = (
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
        f'markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        f'fill="{p.muted}"/></marker></defs>'
    )
    edges, labels, nodes = [], [], []
    for r in content.relations:
        if r.source not in pos or r.target not in pos:
            continue
        (x1, y1, _), (x2, y2, _) = pos[r.source], pos[r.target]
        if x1 == x2:  # misma columna: curva por la derecha
            x1 = x2 = x1 + NODE_W / 2
            bend = x1 + 90
            path = f"M{x1:.1f},{y1:.1f} Q{bend:.1f},{(y1 + y2) / 2:.1f} {x2 + 4:.1f},{y2:.1f}"
            mx, my = x1 + 45, (y1 + y2) / 2
        else:
            ahead = 1 if x2 > x1 else -1
            x1, x2 = x1 + ahead * NODE_W / 2, x2 - ahead * (NODE_W / 2 + 4)
            path = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        edges.append(
            f'<path d="{path}" stroke="{p.muted}" stroke-width="1.6" fill="none" '
            f'marker-end="url(#arrow)"/>'
        )
        lw = len(r.label) * 6.6 + 14
        bounds.add(mx - lw / 2, my - 11, mx + lw / 2, my + 11)
        if x1 == x2:
            bounds.add(x1, y1, x1 + 90, y2)
        labels.append(
            f'<rect x="{mx - lw / 2:.1f}" y="{my - 11:.1f}" width="{lw:.1f}" height="22" '
            f'rx="11" fill="{p.background}"/>'
        )
        labels.append(
            text_block([r.label], mx, my, 12, "middle", fill=p.secondary, font_style="italic")
        )
    for x, y, lines in pos.values():
        h = len(lines) * 18 + 24
        nodes.append(
            f'<rect x="{x - NODE_W / 2:.1f}" y="{y - h / 2:.1f}" width="{NODE_W}" '
            f'height="{h:.1f}" rx="12" fill="{p.surface}" stroke="{p.primary}" '
            f'stroke-width="2"/>'
        )
        nodes.append(text_block(lines, x, y, 14, "middle", fill=p.text, font_weight="700"))
        bounds.add(x - NODE_W / 2, y - h / 2, x + NODE_W / 2, y + h / 2)
    body = marker + "".join(edges) + "".join(labels) + "".join(nodes)
    return bounds.document(body, template)


def concept_map_mermaid(content: ConceptMapContent) -> str:
    def q(text: str) -> str:
        return text.replace('"', "#quot;")

    out = ["flowchart TD"]
    # Prefijo: palabras como "end" son reservadas en Mermaid.
    out += [f'  c_{c.id}["{q(c.label)}"]' for c in content.concepts]
    out += [f'  c_{r.source} -->|"{q(r.label)}"| c_{r.target}' for r in content.relations]
    return "\n".join(out) + "\n"


def concept_map_drawio(content: ConceptMapContent) -> str:
    pos = concept_layout(content)
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    labels = {c.id: c.label for c in content.concepts}
    for node_id, (x, y, _) in pos.items():
        cells.append(
            f"<mxCell id={quoteattr('n-' + node_id)} value={quoteattr(labels[node_id])} "
            'style="rounded=1;whiteSpace=wrap;html=0;fontStyle=1;" vertex="1" parent="1">'
            f'<mxGeometry x="{x - NODE_W / 2:.0f}" y="{y - 30:.0f}" width="{NODE_W}" height="60" '
            'as="geometry"/></mxCell>'
        )
    for i, r in enumerate(content.relations):
        cells.append(
            f'<mxCell id="e-{i}" value={quoteattr(r.label)} style="endArrow=classic;html=0;" '
            f'edge="1" parent="1" source={quoteattr("n-" + r.source)} '
            f'target={quoteattr("n-" + r.target)}><mxGeometry relative="1" as="geometry"/></mxCell>'
        )
    return (
        f'<mxfile host="ProductForge"><diagram name={quoteattr(content.title)}>'
        f"<mxGraphModel><root>{''.join(cells)}</root></mxGraphModel></diagram></mxfile>\n"
    )


# ─────────────────────────── Generadores ───────────────────────────


def fit_box(svg: str, max_w: float, max_h: float) -> tuple[float, float]:
    """Tamaño en mm que conserva la proporción del SVG dentro del área útil de la página."""
    _, _, w, h = (float(v) for v in svg.split('viewBox="', 1)[1].split('"', 1)[0].split())
    scale = min(max_w / w, max_h / h)
    return round(w * scale, 1), round(h * scale, 1)


def svg_pdf_png(
    svg: str, title: str, subtitle: str, template: Template, ctx: RenderContext
) -> tuple[bytes, bytes]:
    svg_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    img_w, img_h = fit_box(svg, max_w=273, max_h=150 if subtitle else 162)
    html = template.render_html(
        "map", svg_uri=svg_uri, title=title, subtitle=subtitle, ctx=ctx, img_w=img_w, img_h=img_h
    )
    pdf = html_to_pdf(html, template.base_dir)
    return pdf, pdf_page_to_png(pdf, width=2000)


@register
class MindMapGenerator:
    format: ClassVar[Format] = Format.MIND_MAP
    outputs: ClassVar[tuple[str, ...]] = ("svg", "png", "pdf", "md", "mmd", "opml", "mm", "xmind")

    def generate(
        self, content: MindMapContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        svg = mind_map_svg(content, template)
        pdf, png = svg_pdf_png(svg, content.title, "", template, ctx)
        return [
            artifact(ctx, "svg", svg.encode()),
            artifact(ctx, "png", png),
            artifact(ctx, "pdf", pdf),
            artifact(ctx, "md", mind_map_markmap(content).encode()),
            artifact(ctx, "mmd", mind_map_mermaid(content).encode()),
            artifact(ctx, "opml", mind_map_opml(content).encode()),
            artifact(ctx, "mm", mind_map_freemind(content).encode()),
            artifact(ctx, "xmind", mind_map_xmind(content)),
        ]


@register
class ConceptMapGenerator:
    format: ClassVar[Format] = Format.CONCEPT_MAP
    outputs: ClassVar[tuple[str, ...]] = ("svg", "png", "pdf", "mmd", "drawio")

    def generate(
        self, content: ConceptMapContent, template: Template, ctx: RenderContext
    ) -> list[FileArtifact]:
        svg = concept_map_svg(content, template)
        subtitle = f"{ctx.labels['focus_question']}: {content.focus_question}"
        pdf, png = svg_pdf_png(svg, content.title, subtitle, template, ctx)
        return [
            artifact(ctx, "svg", svg.encode()),
            artifact(ctx, "png", png),
            artifact(ctx, "pdf", pdf),
            artifact(ctx, "mmd", concept_map_mermaid(content).encode()),
            artifact(ctx, "drawio", concept_map_drawio(content).encode()),
        ]
