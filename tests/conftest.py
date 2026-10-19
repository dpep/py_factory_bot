import pytest

from factory_bot import clear_factories


@pytest.fixture(autouse=True)
def clean_registry():
    clear_factories()
