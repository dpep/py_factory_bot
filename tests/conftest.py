import pytest

from factory_bot import clear_factories, reset_sequences, to_create


@pytest.fixture(autouse=True)
def clean_registry():
    clear_factories()
    reset_sequences()
    to_create(None)
