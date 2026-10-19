import pytest

from factory_bot import clear_factories, persist_with, reset_sequences


@pytest.fixture(autouse=True)
def clean_registry():
    clear_factories()
    reset_sequences()
    persist_with(None)
