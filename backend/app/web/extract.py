"""Extrae de una página de ventas el texto que sirve para entender la oferta.

Solo usa la biblioteca estándar. Lo que se descarta a propósito: scripts, estilos, navegación,
pie, formularios y todo lo oculto (`hidden`, `aria-hidden`, `display:none`, tamaño 0…), que es
donde suelen esconderse instrucciones dirigidas a un modelo de IA. Lo que queda sigue siendo texto
de un tercero: se trata como dato no confiable en los prompts.
"""

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_CHARS = 14_000  # lo que se le pasa a la IA
THIN_CHARS = 400  # menos que esto: casi seguro la página se arma con JavaScript

SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "template",
    "iframe",
    "canvas",
    "nav",
    "footer",
    "aside",
    "form",
    "select",
    "option",
    "button",
    "object",
    "embed",
    "audio",
    "video",
    "map",
    "dialog",
}
BLOCK_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "p",
    "li",
    "blockquote",
    "figcaption",
    "td",
    "th",
    "dt",
    "dd",
    "summary",
    "div",
    "section",
    "article",
    "header",
    "main",
    "tr",
    "ul",
    "ol",
    "br",
}
HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d])"
    r"|height\s*:\s*0(?![.\d])\s*;?[^}]*overflow\s*:\s*hidden|text-indent\s*:\s*-\d{3,}",
    re.IGNORECASE,
)
INVISIBLE_CHARS = re.compile(r"[​-‏⁠-⁤﻿­‪-‮⁦-⁩]")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class PageText:
    title: str
    description: str
    text: str
    offers: str  # precio y oferta tal como los declara la página (JSON-LD), si los hay
    truncated: bool

    @property
    def is_thin(self) -> bool:
        return len(self.text) < THIN_CHARS


def clean(text: str) -> str:
    text = INVISIBLE_CHARS.sub("", CONTROL_CHARS.sub(" ", text))
    return re.sub(r"[ \t\r\f\v ]+", " ", text).strip()


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.lines: list[str] = []
        self._buffer: list[str] = []
        self._hidden_depth = 0  # >0: dentro de algo que no se lee
        self._open: list[tuple[str, bool]] = []  # (etiqueta, oculta)
        self._in_title = False
        self._ld_depth = False
        self._ld: list[str] = []
        self.json_ld: list[str] = []

    # Etiquetas sin cierre: no se apilan.
    _VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "source", "wbr"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {"description", "og:description", "og:title", "twitter:description"}:
                self.meta.setdefault(key, clean(a.get("content", "")))
            return
        if tag == "title":
            self._in_title = True
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._ld_depth = True
        if tag in self._VOID:
            if tag == "br":
                self._flush()
            return
        hidden = (
            tag in SKIP_TAGS
            or "hidden" in a
            or a.get("aria-hidden", "").lower() == "true"
            or bool(HIDDEN_STYLE.search(a.get("style", "")))
            or a.get("type", "").lower() == "hidden"
        )
        self._open.append((tag, hidden))
        if hidden:
            self._hidden_depth += 1
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._ld_depth:
            self._ld_depth = False
            self.json_ld.append("".join(self._ld))
            self._ld = []
        if tag in self._VOID:
            return
        # Cierra hasta la etiqueta que coincide (el HTML real suele venir mal anidado).
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                for _, hidden in self._open[i:]:
                    if hidden:
                        self._hidden_depth -= 1
                del self._open[i:]
                break
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._ld_depth:
            self._ld.append(data)
        elif self._hidden_depth == 0:
            self._buffer.append(data)

    def _flush(self) -> None:
        line = clean(" ".join(self._buffer))
        self._buffer = []
        if line:
            self.lines.append(line)

    def close(self) -> None:
        super().close()
        self._flush()


def _offers(blocks: list[str]) -> str:
    """Precio/oferta declarados en JSON-LD (schema.org), si la página los publica."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = str(node.get("@type", ""))
            if "Offer" in kind or "Product" in kind:
                bits = [
                    str(node.get(k))
                    for k in ("name", "price", "lowPrice", "highPrice", "priceCurrency")
                    if node.get(k) not in (None, "")
                ]
                if bits:
                    found.append(" ".join(bits))
            for value in node.values():
                if isinstance(value, dict | list):
                    walk(value)

    for block in blocks:
        try:
            walk(json.loads(block))
        except ValueError:
            continue
    return clean("; ".join(dict.fromkeys(found)))[:400]


def extract_text(html: str, *, truncated: bool = False) -> PageText:
    parser = _Parser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # HTML muy roto: se usa lo que se alcanzó a leer
        parser._flush()
    lines: list[str] = []
    seen: set[str] = set()
    total = 0
    for line in parser.lines:
        key = line.lower()
        if key in seen or len(line) < 3:
            continue  # el mismo texto repetido (menús, versiones móvil/escritorio)
        seen.add(key)
        if total + len(line) + 1 > MAX_CHARS:
            truncated = True
            break
        lines.append(line)
        total += len(line) + 1
    description = parser.meta.get("description") or parser.meta.get("og:description") or ""
    return PageText(
        title=clean(parser.title or parser.meta.get("og:title", ""))[:300],
        description=description[:500],
        text="\n".join(lines),
        offers=_offers(parser.json_ld),
        truncated=truncated,
    )


def clean_pasted_text(text: str) -> PageText:
    """Texto que el usuario pegó a mano (cuando la página no se puede leer sola)."""
    lines = [clean(line) for line in text.splitlines()]
    body = "\n".join(line for line in lines if len(line) >= 3)[:MAX_CHARS]
    return PageText(title="", description="", text=body, offers="", truncated=len(text) > MAX_CHARS)
