"""Fotos de capítulo: la que se elige debe mostrar la escena, no solo ser popular."""

import asyncio
import io

import httpx
import pytest
from PIL import Image

from app.ads.images.base import ImageRequest, ProviderRejected
from app.ads.images.pixabay import PixabayProvider


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), "#335577").save(out, "JPEG")
    return out.getvalue()


def hit(n: int, tags: str) -> dict:
    return {
        "id": n,
        "user": "autor",
        "pageURL": f"https://pixabay.com/photos/x-{n}/",
        "tags": tags,
        "largeImageURL": f"https://pixabay.com/get/x-{n}.jpg",
        "imageWidth": 1920,
        "imageHeight": 1080,
    }


SWIMMER = hit(1, "swimming, jumping, pool, sport")  # popular pero no es la escena
KIDS = hit(2, "children, jumping, cardboard, boxes, playground, school")
REQUEST = ImageRequest(
    prompt="children jumping over cardboard boxes in a school playground",
    keywords=("kids jumping", "cardboard boxes"),
    aspect="16:9",
    curate=True,
    context="Cajas saltarinas",
)


def provider(hits: list[dict], curator=None, log: list | None = None) -> PixabayProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(request)
        if request.url.path == "/api/":
            return httpx.Response(200, json={"hits": hits})
        return httpx.Response(200, content=jpeg(), headers={"content-type": "image/jpeg"})

    return PixabayProvider(
        "k", httpx.AsyncClient(transport=httpx.MockTransport(handler)), curator=curator
    )


class Curator:
    def __init__(self, answer: int | None = None, fail: bool = False) -> None:
        self.answer, self.fail, self.seen = answer, fail, []

    async def choose(self, scene: str, context: str, tags: list[str]) -> int | None:
        self.seen.append((scene, context, tags))
        if self.fail:
            raise RuntimeError("sin red")
        return self.answer


def test_without_a_curator_the_photo_closest_to_the_scene_wins_over_the_popular_one() -> None:
    plain = ImageRequest(REQUEST.prompt, REQUEST.keywords, "16:9")
    image = asyncio.run(provider([SWIMMER, KIDS]).fetch(plain))
    assert image.credit["id"] == 2


def test_the_curator_sees_the_scene_and_its_pick_is_used() -> None:
    curator = Curator(answer=1)
    image = asyncio.run(provider([SWIMMER, KIDS], curator).fetch(REQUEST))
    scene, context, tags = curator.seen[0]
    assert scene == REQUEST.prompt and context == "Cajas saltarinas"
    assert len(tags) == 2 and "swimming" in tags[0] + tags[1]
    # Con la más parecida por etiquetas primero, el índice 1 es la nadadora.
    assert image.credit["id"] == 1


def test_a_curator_that_finds_no_fitting_photo_leaves_the_chapter_without_one() -> None:
    with pytest.raises(ProviderRejected):
        asyncio.run(provider([SWIMMER, KIDS], Curator(answer=None)).fetch(REQUEST))


def test_a_failing_curator_falls_back_to_the_closest_by_tags() -> None:
    image = asyncio.run(provider([SWIMMER, KIDS], Curator(fail=True)).fetch(REQUEST))
    assert image.credit["id"] == 2


def test_curated_requests_do_not_share_cache_with_plain_ones() -> None:
    plain = ImageRequest(REQUEST.prompt, REQUEST.keywords, "16:9")
    assert plain.scene_hash("u") != REQUEST.scene_hash("u")


def test_the_most_specific_search_goes_first_and_only_loosens_when_empty() -> None:
    log: list = []
    asyncio.run(provider([KIDS], log=log).fetch(REQUEST))
    assert log[0].url.params["q"] == "kids jumping cardboard boxes"
    assert len([r for r in log if r.url.path == "/api/"]) == 1
