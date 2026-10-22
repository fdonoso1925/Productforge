"""El backend lee páginas que indica el usuario: no puede servir para llegar a redes internas."""

import asyncio
import gzip
import socket

import httpx
import pytest

from app.web import safe_fetch
from app.web.safe_fetch import (
    MAX_BYTES,
    FetchError,
    UnsafeUrl,
    fetch_page,
    resolve_public,
    validate_url,
)

PUBLIC = "93.184.216.34"
HTML = b"<html><head><title>Oferta</title></head><body><h1>Titulo</h1><p>Hola</p></body></html>"


def run(coro):
    return asyncio.run(coro)


async def public_resolver(host: str, port: int) -> list[str]:
    return [PUBLIC]


class Recorder:
    """Transporte falso: registra cada petición que 'saldría' a la red."""

    def __init__(self, handler) -> None:
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)
        self._handler = handler

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self._handler(request)
        return await result if asyncio.iscoroutine(result) else result


def page(body: bytes = HTML, content_type: str = "text/html; charset=utf-8", status: int = 200):
    return lambda request: httpx.Response(
        status, content=body, headers={"content-type": content_type}
    )


# ───────────────────────────── validación de la URL ─────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://ejemplo.com/oferta",
        "http://ejemplo.com",
        "https://sub.ejemplo.com.br/p?a=1#x",
        "https://ejemplo.com:443/x",
        "http://ejemplo.com:80/x",
        "https://93.184.216.34/pagina",
    ],
)
def test_normal_public_urls_are_accepted(url: str) -> None:
    validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "ejemplo.com",
        "//ejemplo.com",
        "ftp://ejemplo.com/a",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>1</script>",
        "gopher://ejemplo.com",
        "https://usuario:clave@ejemplo.com",
        "https://usuario@ejemplo.com",
        "https://ejemplo.com:8080/",
        "https://ejemplo.com:22/",
        "http://ejemplo.com:6379/",
        "https://ejemplo.com:99999/",
        "https://localhost/",
        "http://LOCALHOST./",
        "https://127.0.0.1/",
        "https://127.1.2.3/",
        "https://0.0.0.0/",
        "https://[::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://10.0.0.5/",
        "https://172.16.0.1/",
        "https://192.168.1.1/",
        "https://169.254.169.254/latest/meta-data/",
        "https://[fd00:ec2::254]/",
        "https://100.64.0.1/",
        "https://224.0.0.1/",
        "http://metadata/computeMetadata/v1/",
        "https://servidor.internal/",
        "https://impresora.local/",
        "https://router.lan/",
        "https://ejemplo.com/a b",
        "https://ejemplo.com/a\r\nHost: evil",
        "https://ejemplo.com/" + "a" * 2100,
        "http://[::1",
    ],
)
def test_dangerous_or_malformed_urls_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        validate_url(url)


# ───────────────────────────── resolución de nombres ─────────────────────────────


def test_numeric_tricks_that_resolve_to_loopback_are_blocked() -> None:
    # Formas "creativas" de escribir 127.0.0.1: el sistema las resuelve a loopback.
    for host in ("2130706433", "0x7f000001", "127.1", "0177.0.0.1"):
        with pytest.raises(FetchError):
            run(resolve_public(host, 80))


def test_every_resolved_address_must_be_public(monkeypatch) -> None:
    answers: list[str] = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", (a, port)) for a in answers]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    def resolve(*addrs: str) -> list[str]:
        answers[:] = addrs
        return run(resolve_public("ejemplo.com", 443))

    assert resolve(PUBLIC) == [PUBLIC]
    with pytest.raises(UnsafeUrl):
        resolve(PUBLIC, "10.0.0.1")  # una sola privada basta para rechazar
    with pytest.raises(UnsafeUrl):
        resolve("::ffff:169.254.169.254")
    with pytest.raises(UnsafeUrl):
        resolve()


def test_unknown_names_give_a_friendly_error() -> None:
    with pytest.raises(FetchError, match="no se encontró"):
        run(resolve_public("este-dominio-no-existe.invalid", 443))


# ───────────────────────────── lectura de páginas ─────────────────────────────


def test_a_normal_page_is_read_connecting_to_the_validated_ip() -> None:
    rec = Recorder(page())
    result = run(
        fetch_page(
            "https://ejemplo.com/oferta?x=1", resolver=public_resolver, transport=rec.transport
        )
    )
    assert "Titulo" in result.html and not result.truncated
    [request] = rec.requests
    assert request.url.host == PUBLIC  # conecta a la IP ya revisada, no vuelve a resolver
    assert request.headers["host"] == "ejemplo.com"
    assert (
        request.extensions["sni_hostname"] == "ejemplo.com"
    )  # y verifica el certificado del nombre
    assert request.url.path == "/oferta" and request.url.query == b"x=1"
    assert "ProductForge" in request.headers["user-agent"]
    assert "cookie" not in request.headers and "authorization" not in request.headers


def test_http_pages_get_no_sni_and_non_default_host_header_is_exact() -> None:
    rec = Recorder(page())
    run(fetch_page("http://ejemplo.com/x", resolver=public_resolver, transport=rec.transport))
    assert "sni_hostname" not in rec.requests[0].extensions
    assert rec.requests[0].headers["host"] == "ejemplo.com"


def test_ipv6_addresses_are_pinned_too() -> None:
    async def v6(host, port):
        return ["2606:2800:220:1:248:1893:25c8:1946"]

    rec = Recorder(page())
    run(fetch_page("https://ejemplo.com/", resolver=v6, transport=rec.transport))
    assert rec.requests[0].url.host == "2606:2800:220:1:248:1893:25c8:1946"


def test_a_private_resolution_never_sends_a_request() -> None:
    async def private(host, port):
        raise UnsafeUrl("esa dirección no es pública")

    rec = Recorder(page())
    with pytest.raises(UnsafeUrl):
        run(fetch_page("https://trampa.example/", resolver=private, transport=rec.transport))
    assert rec.requests == []


def test_a_blocked_url_never_reaches_the_network() -> None:
    rec = Recorder(page())
    for url in (
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/",
        "https://localhost/",
        "file:///etc/passwd",
    ):
        with pytest.raises(UnsafeUrl):
            run(fetch_page(url, resolver=public_resolver, transport=rec.transport))
    assert rec.requests == []


def redirect(location: str, status: int = 302):
    return lambda request: httpx.Response(status, headers={"location": location})


def test_a_redirect_to_an_internal_address_is_blocked_before_following_it() -> None:
    rec = Recorder(redirect("http://169.254.169.254/latest/meta-data/iam/"))
    with pytest.raises(UnsafeUrl):
        run(fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport))
    assert len(rec.requests) == 1  # la segunda petición nunca salió


def test_a_redirect_to_a_name_that_resolves_privately_is_blocked() -> None:
    async def resolver(host: str, port: int) -> list[str]:
        if host == "interno.ejemplo.com":
            raise UnsafeUrl("esa dirección no es pública")
        return [PUBLIC]

    rec = Recorder(redirect("https://interno.ejemplo.com/admin"))
    with pytest.raises(UnsafeUrl):
        run(fetch_page("https://ejemplo.com/", resolver=resolver, transport=rec.transport))
    assert len(rec.requests) == 1


@pytest.mark.parametrize(
    "target",
    ["file:///etc/passwd", "ftp://ejemplo.com/x", "javascript:1", "http://localhost:8000/"],
)
def test_redirects_to_other_schemes_or_ports_are_blocked(target: str) -> None:
    rec = Recorder(redirect(target))
    with pytest.raises(UnsafeUrl):
        run(fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport))
    assert len(rec.requests) == 1


def test_relative_redirects_are_followed_and_revalidated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/inicio":
            return httpx.Response(301, headers={"location": "/oferta"})
        return httpx.Response(200, content=HTML, headers={"content-type": "text/html"})

    rec = Recorder(handler)
    result = run(
        fetch_page("https://ejemplo.com/inicio", resolver=public_resolver, transport=rec.transport)
    )
    assert result.url == "https://ejemplo.com/oferta"
    assert [r.url.path for r in rec.requests] == ["/inicio", "/oferta"]


def test_endless_redirects_stop() -> None:
    rec = Recorder(redirect("/otra"))
    with pytest.raises(FetchError, match="demasiadas veces"):
        run(fetch_page("https://ejemplo.com/a", resolver=public_resolver, transport=rec.transport))
    assert len(rec.requests) == safe_fetch.MAX_REDIRECTS + 1


def test_redirect_without_location_is_an_error() -> None:
    rec = Recorder(lambda r: httpx.Response(302))
    with pytest.raises(FetchError, match="redirige"):
        run(fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport))


@pytest.mark.parametrize("status", [403, 404, 410, 500, 503])
def test_http_errors_become_friendly_messages(status: int) -> None:
    rec = Recorder(page(status=status))
    with pytest.raises(FetchError, match=str(status)):
        run(fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport))


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "image/png", "application/zip", "application/octet-stream", "video/mp4"],
)
def test_only_web_pages_are_read(content_type: str) -> None:
    rec = Recorder(page(b"%PDF-1.7", content_type=content_type))
    with pytest.raises(FetchError, match="no es una página web"):
        run(fetch_page("https://ejemplo.com/a", resolver=public_resolver, transport=rec.transport))


def test_plain_text_is_accepted() -> None:
    rec = Recorder(page(b"solo texto", content_type="text/plain"))
    assert (
        run(
            fetch_page("https://ejemplo.com/a", resolver=public_resolver, transport=rec.transport)
        ).html
        == "solo texto"
    )


def test_huge_pages_are_cut_at_the_limit() -> None:
    rec = Recorder(page(b"a" * (MAX_BYTES + 50_000)))
    result = run(
        fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport)
    )
    assert result.truncated and len(result.html) == MAX_BYTES


def test_a_compression_bomb_is_limited_by_the_decompressed_size() -> None:
    bomb = gzip.compress(b"a" * 20_000_000)  # ~20 KB en el cable, 20 MB al abrir
    assert len(bomb) < 100_000
    rec = Recorder(
        lambda r: httpx.Response(
            200, content=bomb, headers={"content-type": "text/html", "content-encoding": "gzip"}
        )
    )
    result = run(
        fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport)
    )
    assert result.truncated and len(result.html) <= MAX_BYTES


def test_declared_charsets_are_respected_and_unknown_ones_do_not_crash() -> None:
    latin = "<p>Ação rápida — preço</p>".encode("iso-8859-1", errors="replace")
    ok = Recorder(page(latin, content_type="text/html; charset=iso-8859-1"))
    assert (
        "Ação rápida"
        in run(
            fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=ok.transport)
        ).html
    )
    weird = Recorder(page(b"<p>hola</p>", content_type="text/html; charset=inventado-9"))
    assert (
        "hola"
        in run(
            fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=weird.transport)
        ).html
    )


def test_connection_problems_and_timeouts_are_friendly() -> None:
    def boom(request):
        raise httpx.ConnectError("conexión rechazada")

    with pytest.raises(FetchError, match="no se pudo conectar"):
        run(
            fetch_page(
                "https://ejemplo.com/", resolver=public_resolver, transport=Recorder(boom).transport
            )
        )

    def slow(request):
        raise httpx.ReadTimeout("lento")

    with pytest.raises(FetchError, match="tardó demasiado"):
        run(
            fetch_page(
                "https://ejemplo.com/", resolver=public_resolver, transport=Recorder(slow).transport
            )
        )


def test_the_total_time_is_capped(monkeypatch) -> None:
    monkeypatch.setattr(safe_fetch, "TOTAL_SECONDS", 0.05)

    async def never(request):
        await asyncio.sleep(5)
        return httpx.Response(200, content=HTML)

    with pytest.raises(FetchError, match="tardó demasiado"):
        run(
            fetch_page(
                "https://ejemplo.com/",
                resolver=public_resolver,
                transport=Recorder(never).transport,
            )
        )


def test_environment_proxies_are_ignored(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.interno:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.interno:3128")
    rec = Recorder(page())
    run(fetch_page("https://ejemplo.com/", resolver=public_resolver, transport=rec.transport))
    assert rec.requests[0].url.host == PUBLIC  # no se desvió a un proxy
