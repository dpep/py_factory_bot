# factory_bot

Generate realistic test data with ease.

Describe your test data once, and every test can ask for it: `build(user)`, `create(user, "admin", first_name="Jane")`, `build_list(post, 3)`. Each test spells out only the fields it cares about, and the factory fills in the rest, with believable fake values from [Faker](https://faker.readthedocs.io) when you ask for them. It works with anything that takes keyword arguments: plain classes, dataclasses, dicts, Django and SQLAlchemy models. Under pytest, every test gets the same fake data whether it runs alone, in the suite, or in a different order.

Early development: the API is still settling.


## Install

```
pip install factory_bot
```


## Quick start

```python
from dataclasses import dataclass

from factory_bot import build, create, f, factory, fake, sequence, trait


@dataclass
class User:
    first_name: str
    last_name: str
    email: str
    username: str
    admin: bool = False

    def save(self):
        pass  # your ORM's save(); create() calls it


@factory(User)
def user():
    f.first_name = fake.first_name  # no parens: a fresh name on every build
    f.last_name = fake.last_name
    f.email = lambda first_name, last_name: f"{first_name}.{last_name}@example.com"
    f.username = sequence(lambda n: f"user{n}")

    @trait
    def admin():
        f.admin = True


build(user)
# User(first_name='Diane', last_name='Butler', email='Diane.Butler@example.com', username='user1', admin=False)

create(user, "admin", first_name="Jane")
# User(first_name='Jane', last_name='Turner', email='Jane.Turner@example.com', username='user2', admin=True)
```

A factory is a plain function that assigns attributes to `f`: no classes, no `Meta`. A function value, like `email`'s lambda, is called on every build, with its parameters filled from the attributes of the same name. So overrides like `first_name="Jane"` win, and `email` follows along. Later traits win over earlier ones, and overrides beat them all.

`@factory` returns the factory, so `build(user)` is typed as a `User`. Its name works too: `build("user")`.


## Associations

```python
from factory_bot import association


@factory(dict)
def author():
    f.name = "Ann"


@factory(dict)
def book():
    f.title = "Dune"
    f.author = association(author, name="Frank")


assert build(book) == {"title": "Dune", "author": {"name": "Frank"}}
assert build(book, author_id=7) == {"title": "Dune", "author_id": 7}
```

An association follows the parent: `build` builds it, and `create` creates it first, so it's saved before the row that points at it. Pass your own with `author=`, or `author_id=` to skip making one.


## Saving

`create` builds, then calls `obj.save()`. A Django model needs nothing more.

For SQLAlchemy, hand `persist_with` the test's session. Each created object is added and flushed, so ids and foreign keys are set, but nothing is committed:

<!-- skip-doctest -->
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from factory_bot import persist_with
from myapp.models import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        persist_with(session)  # undone when the fixture ends
        yield session
```

For anything else, `persist_with(fn)` saves with your function. The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#sqlalchemy-fixtures) has a fixture that rolls back an outer transaction instead.


## The same data alone or in the suite

The pytest plugin is on as soon as factory_bot is installed. It reseeds `fake` for every test and every fixture from the run's seed and the test's or fixture's id. So a test that fails in the suite fails with the same names and emails when you run it alone, in another order, or under pytest-xdist. The seed is in the header:

```
factory_bot: seed=0, reset_sequences=off
```

With [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), its seed drives this one: each run gets new data, and `--randomly-seed=N` replays a run's. Sequences keep counting across tests; [test isolation](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#test-isolation) shows how to restart them. To turn the plugin off, run `pytest -p no:factory_bot`.


## Learn more

The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md) has the rest:

- [The value rule](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#the-value-rule), [sequences, traits, transients and callbacks](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#declaring-attributes), [child factories](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#child-factories)
- [Associations](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#associations), [has-many](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#has-many) and [strategies](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#strategies)
- [Faker](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#faker), [gotchas](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#gotchas) and [type checkers](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#type-checkers)
- [Organizing factories](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#organizing-factories) and [test isolation](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#test-isolation)
- Recipes for [Django](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#django-many-to-many), [SQLAlchemy](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#sqlalchemy-fixtures) and [checking every factory](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#checking-every-factory)
- [Error messages](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#error-messages)

Inspired by thoughtbot's [factory_bot](https://github.com/thoughtbot/factory_bot) for Ruby.

----
[![installs](https://img.shields.io/pypi/dm/factory_bot?label=installs)](https://pypi.org/project/factory_bot)
