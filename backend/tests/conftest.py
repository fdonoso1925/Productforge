import pytest

from app.security import limiter


@pytest.fixture(autouse=True)
def _fresh_rate_limiter() -> None:
    """El límite vive en memoria y es global: cada test parte de cero."""
    limiter.reset()
