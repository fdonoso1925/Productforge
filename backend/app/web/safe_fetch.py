"""Lee una página web que indicó el usuario, sin que el backend pueda usarse para llegar a redes
internas (SSRF).

Defensas, todas obligatorias:
- solo http/https, puertos 80/443, sin usuario:clave en la URL;
- el nombre se resuelve ANTES de conectar y todas las direcciones deben ser públicas (no loopback,
  privadas, link-local —ahí vive el servicio de metadatos de la nube—, CGNAT ni reservadas);
- la conexión va a la IP ya validada (con el nombre original en `Host` y en el SNI), así una
  respuesta DNS distinta en un segundo intento no sirve (DNS rebinding);
- las redirecciones se siguen a mano, y cada salto pasa otra vez por todo lo anterior;
- tiempo, tamaño y tipo de contenido acotados; sin proxies del entorno ni cookies.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
MAX_URL_LENGTH = 2000
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 4
TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
TOTAL_SECONDS = 20.0
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
USER_AGENT = "Mozilla/5.0 (compatible; ProductForge/1.0; uso personal)"
BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")

Resolver = Callable[[str, int], Awaitable[list[str]]]


class FetchError(Exception):
    """No se pudo leer la página; el mensaje es apto para mostrarlo al usuario."""


class UnsafeUrl(FetchError):
    """La dirección no es pública o no es una URL web válida."""


@dataclass(frozen=True)
class FetchedPage:
    url: str  # URL final, tras las redirecciones
    html: str
    truncated: bool


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 es el 127.0.0.1 de siempre
    return ip.is_global and not ip.is_multicast


def validate_url(url: str) -> tuple[str, str, int]:
    """Devuelve (esquema, host, puerto) si la URL es aceptable; si no, `UnsafeUrl`."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LENGTH or any(c in url for c in "\r\n\t "):
        raise UnsafeUrl("la dirección no es válida")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrl("la dirección no es válida") from exc
    if parts.scheme not in ALLOWED_SCHEMES or not parts.hostname:
        raise UnsafeUrl("usa una dirección que empiece con http:// o https://")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrl("la dirección no puede llevar usuario ni clave")
    port = port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeUrl("solo se pueden leer páginas web normales (puertos 80 y 443)")
    host = parts.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata"} or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeUrl("esa dirección no es pública")
    try:
        if not _is_public(host):  # IP escrita directamente
            raise UnsafeUrl("esa dirección no es pública")
    except ValueError:
        pass  # no es una IP: es un nombre, se valida al resolverlo
    return parts.scheme, host, port


async def resolve_public(host: str, port: int) -> list[str]:
    """Resuelve el nombre y exige que TODAS las direcciones sean públicas."""
    try:
        ip = ipaddress.ip_address(host)
        addresses = [str(ip)]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise FetchError("no se encontró esa página (revisa la dirección)") from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeUrl("esa dirección no es pública")
    return addresses


async def fetch_page(
    url: str,
    *,
    resolver: Resolver = resolve_public,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedPage:
    try:
        async with asyncio.timeout(TOTAL_SECONDS):
            return await _fetch(url, resolver, transport)
    except TimeoutError as exc:
        raise FetchError("la página tardó demasiado en responder") from exc


async def _fetch(url: str, resolver: Resolver, transport) -> FetchedPage:
    current = url.strip()
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=False,
        trust_env=False,  # ignora HTTP_PROXY y similares: la conexión es directa
        transport=transport,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port = validate_url(current)
            address = (await resolver(host, port))[0]
            pinned = httpx.URL(current).copy_with(host=address)
            extensions = {"sni_hostname": host} if scheme == "https" else {}
            try:
                async with client.stream(
                    "GET",
                    pinned,
                    headers={"Host": _host_header(host, port, scheme)},
                    extensions=extensions,
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("la página redirige a ninguna parte")
                        current = urljoin(current, location)
                        continue
                    return await _read(response, current)
            except httpx.InvalidURL as exc:  # p. ej. una redirección a «javascript:»
                raise UnsafeUrl("la página redirige a una dirección no válida") from exc
            except httpx.TimeoutException as exc:
                raise FetchError("la página tardó demasiado en responder") from exc
            except httpx.HTTPError as exc:
                raise FetchError("no se pudo conectar con esa página") from exc
    raise FetchError("la página redirige demasiadas veces")


def _host_header(host: str, port: int, scheme: str) -> str:
    default = 443 if scheme == "https" else 80
    shown = f"[{host}]" if ":" in host else host
    return shown if port == default else f"{shown}:{port}"


async def _read(response: httpx.Response, url: str) -> FetchedPage:
    if response.status_code >= 400:
        raise FetchError(
            f"la página respondió con error {response.status_code} "
            "(algunas páginas bloquean las lecturas automáticas)"
        )
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type and not content_type.startswith(TEXT_TYPES):
        raise FetchError("esa dirección no es una página web (es otro tipo de archivo)")
    chunks: list[bytes] = []
    size = 0
    truncated = False
    async for chunk in response.aiter_bytes():  # ya descomprimido: el tope cuenta lo real
        size += len(chunk)
        if size > MAX_BYTES:
            chunks.append(chunk[: len(chunk) - (size - MAX_BYTES)])
            truncated = True
            break
        chunks.append(chunk)
    charset = response.charset_encoding or "utf-8"
    try:
        html = b"".join(chunks).decode(charset, errors="replace")
    except LookupError:
        html = b"".join(chunks).decode("utf-8", errors="replace")
    return FetchedPage(url=url, html=html, truncated=truncated)
