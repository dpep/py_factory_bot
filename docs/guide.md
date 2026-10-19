# factory_bot guide

The [README](https://github.com/dpep/py_factory_bot/blob/main/README.md) is the tour. This is the manual: the one rule that decides what every attribute becomes, the mistakes that rule makes easy, how to keep tests isolated, recipes for the patterns real suites need, and what each error message means.

- [How a factory works](#how-a-factory-works)
- [The value rule](#the-value-rule)
- [Gotchas](#gotchas)
- [Strategies and callbacks in detail](#strategies-and-callbacks-in-detail)
- [Organizing factories](#organizing-factories)
- [Test isolation](#test-isolation)
- [Recipes](#recipes)
- [Error messages](#error-messages)
- [API at a glance](#api-at-a-glance)
- [Type checkers](#type-checkers)


## How a factory works

A factory body is a recipe card, not a meal. It runs once, when Python reaches the `@factory` line, and writes down what each attribute should be. Every `build` cooks a fresh object from that card: it works out each attribute, then calls the model with them as keyword arguments.

```python
from factory_bot import build, f, factory, sequence


@factory(dict)
def user():
    f.name = "Ann"
    f.username = sequence(lambda n: f"user{n}")


assert build("user") == {"name": "Ann", "username": "user1"}
assert build("user", name="Bea") == {"name": "Bea", "username": "user2"}
```

The model is any callable that takes keyword arguments: a class, a dataclass, `dict`, a Django or SQLAlchemy model, a plain function. Factory names are global, so define each one once, and every test can build it by name.

When the same attribute is set in several places, the most specific wins:

1. overrides passed to `build(...)`
2. traits, in the order listed (the last one wins)
3. the child factory
4. its parent

Overrides may also name attributes the factory never declared; they go straight to the model.


## The value rule

Every attribute, wherever it was declared, becomes a value on each build by one rule:

- **A marker** does its job. `sequence(fn)` calls `fn` with the next number of its own counter, starting at 1. `association("name", *traits, **overrides)` makes that factory's object. `transient(value)` resolves `value` by this same rule but keeps the result away from the model.
- **A callable** is called, on every build, unless it's a class: a class is stored as-is. Each parameter without a default is filled with the attribute of the same name. Parameters with defaults, `*args` and `**kwargs` are left alone, and a callable with no readable signature is called with nothing.
- **A list, dict or set** is copied, so builds never share one.
- **Anything else** is used as-is, and every build gets that same object.
- **An override** is used exactly as given. It's never called, even when it's a function.

Each attribute is worked out at most once per build, so everything that depends on it sees the same value.

```python
from factory_bot import fake


@factory(dict)
def person():
    f.first_name = fake.first_name  # a callable: a fresh name per build
    f.email = lambda first_name: f"{first_name}@example.com".lower()  # a dependency
    f.username = lambda first_name: first_name.lower()  # sees the same first_name
    f.bio = fake.paragraph  # its parameters all have defaults, so nothing is injected
    f.tags = []  # copied per build
    f.country = "NZ"  # used as-is


someone = build("person")
assert someone["email"] == f"{someone['username']}@example.com"


def notify():
    pass


@factory(dict)
def job():
    f.on_done = lambda: None


assert build("job", on_done=notify)["on_done"] is notify  # overrides are never called
```


## Gotchas

The value rule is short, but four of its consequences catch almost everyone once.

### `fake.first_name()` with parentheses is an error

The parentheses would call it right away, while the body runs, so the factory would record one string and hand it to every build. factory_bot raises a `FactoryError` instead: `fake.first_name() was called while the factory was being defined`.

Drop the parentheses so the method itself is the value, or wrap a call that needs arguments in a lambda: `f.age = lambda: fake.random_int(min=18, max=90)`.

### A class is stored, not called

A class is a value like any other: `f.status = Status` stores the `Enum` class itself, and `f.kind = Decimal` stores `Decimal`. For an instance per build, call it in a lambda:

```python
from decimal import Decimal


@factory(dict)
def price():
    f.amount_type = Decimal
    f.amount = lambda: Decimal("9.99")


assert build("price") == {"amount_type": Decimal, "amount": Decimal("9.99")}
```

Any other callable is called. To store one, like a `Mock()` or a handler function, wrap it in a lambda that returns it:

```python
from unittest.mock import Mock

client = Mock()


@factory(dict)
def service():
    f.client = lambda: client  # f.client = client would store client()


assert build("service")["client"] is client
```

For an instance of another model, use an [association](#has-many), or call it in a lambda: `f.address = lambda: Address(city="Wellington")`.

### Bodies run once, at definition time

Any code in a body runs once, not per build. A timestamp, a random choice or a helper variable is frozen into the factory:

```python
import random
from datetime import datetime


@factory(dict)
def visit():
    f.at = datetime.now()  # frozen: the time the module was imported
    f.lucky = random.choice([1, 2, 3])  # frozen too
    f.seen_at = datetime.now  # per build
    f.score = lambda: random.choice([1, 2, 3])  # per build
```

The rule of thumb: if it should differ per build, it belongs in a callable.

### `f` is write-only

`f` records what you assign; there's nothing to read back yet, because no build has happened. Reading raises a `FactoryError` that names the fix: take the other attribute as a parameter.

```python
@factory(dict)
def contact():
    f.first_name = "Ann"
    f.email = lambda first_name: f"{first_name}@example.com"  # not f.first_name + "..."
```

## Strategies and callbacks in detail

| | returns | `after_build` | saved | `after_create` | associations |
|---|---|---|---|---|---|
| `build` | the object | runs | no | no | built |
| `create` | the object | runs | yes | runs | created |
| `attributes_for` | a dict | no | no | no | left out |

`build_list` and `create_list` call `build` or `create` once per object, with the same traits and overrides. Transients never appear in any result.

`after_create` doesn't run on `build`, so anything an `after_create` callback adds, like the children in the [has-many recipe](#has-many), is missing from a built object.

`attributes_for` leaves out associations and transients. What's left are the attributes as Python objects, so a date is a `date` and a lazy attribute that built something returns that object: it's ready to pass to a constructor or a form, but it isn't JSON. An association left out is still built when another attribute depends on it:

```python
from factory_bot import association, attributes_for


@factory(dict)
def writer():
    f.name = "Ann"


@factory(dict)
def essay():
    f.writer = association("writer")
    f.byline = lambda writer: f"by {writer['name']}"


assert attributes_for("essay") == {"byline": "by Ann"}
```

A callback's first parameter is the object, whatever you name it; the rest are filled by name, like a lazy attribute, and may name transients. Callbacks can live in a factory, a child or a trait, and run in that order: parent, child, then each trait in the order listed. `after_build` runs on `create` too, before the save, which is where anything that must be saved with the row belongs.

`create` saves with the global `to_create(fn)` hook if one is set, otherwise `obj.save()`. The hook is one setting for the whole process, not per thread.


## Organizing factories

Put every factory in one module, `tests/factories.py`, and import it once from `tests/conftest.py`. The import registers them all before any test runs, and the registry's names give everyone one place to look.

```
tests/
├── conftest.py
├── factories.py
└── test_users.py
```

<!-- skip-doctest -->
```python
# tests/factories.py
from factory_bot import f, factory, fake, sequence, trait
from myapp.models import User


@factory(User)
def user():
    f.name = fake.name
    f.email = sequence(lambda n: f"user{n}@example.com")

    @trait
    def admin():
        f.is_admin = True
```

<!-- skip-doctest -->
```python
# tests/conftest.py
import factories  # noqa: F401  # registers every factory
```

Tests then just build: `from factory_bot import build`, no import of `factories` needed.

`import factories` works with pytest's default import mode when `tests/` has no `__init__.py`, because pytest puts the conftest's directory on `sys.path`. If `tests/` is a package, write `from . import factories` instead. Under `--import-mode=importlib`, add `pythonpath = ["tests"]` to your pytest config.

When one file gets long, make `factories` a package and import each module from its `__init__.py`.

Factories are global, so define them at module level, not inside tests or fixtures: a factory defined in a fixture is defined again by the next test, and raises `Factory 'user' is already defined`. In a REPL, or before reloading a factories module, call `clear_factories()` to start over.


## Test isolation

What the pytest plugin resets before each test, and what it leaves to you:

- **`fake` is reseeded** from the run's seed and the test's id, so a test's fake data doesn't depend on which tests ran before it. With pytest-randomly installed, each run picks a new seed; rerun with `--randomly-seed=N` (the header shows `N`) to get the same data back. That holds per test: a module- or session-scoped fixture is set up once, under the seed of the first test that uses it, so its data can change with which tests run and in what order.
- **Sequences keep counting** across tests, so `user1` when a test runs alone can be `user7` in the suite. That's the default because restarting them breaks suites that keep rows between tests: two tests that both create `user1` collide on a unique column. If every test rolls back, as with Django's `TestCase` or the SQLAlchemy recipe below, restart them per test:

  ```toml
  [tool.pytest.ini_options]
  factory_bot_reset_sequences = true
  ```

  Or call `reset_sequences()` yourself.
- **`to_create(fn)` is global**, for every thread, and outlives the fixture that set it. Reset it with `to_create(None)` in the fixture's teardown, as the [SQLAlchemy recipe](#sqlalchemy-fixtures) does.
- **Database rows** are your test framework's job. Django's `TestCase` and the SQLAlchemy recipe both roll back.

A test that asserts on a sequence value is the classic way to pass alone and fail in the suite. Pass the value you assert on as an override instead.


## Recipes

### Has-many

A transient count plus an `after_create` callback creates the children once the parent is saved, so they can point at it.

```python
from dataclasses import dataclass, field

from factory_bot import (
    after_create,
    association,
    create,
    create_list,
    f,
    factory,
    fake,
    trait,
    transient,
)


@dataclass
class Author:
    name: str
    books: list = field(default_factory=list)

    def save(self):
        pass


@dataclass
class Book:
    title: str
    author: Author

    def save(self):
        self.author.books.append(self)  # what an ORM's back-reference does for you


@factory(Book)
def book():
    f.title = fake.catch_phrase
    f.author = association("author")


@factory(Author)
def author():
    f.name = fake.name
    f.book_count = transient(0)

    @after_create
    def add_books(author, book_count):
        create_list("book", book_count, author=author)

    @trait
    def prolific():
        f.book_count = transient(10)


assert len(create("author", book_count=3).books) == 3
assert len(create("author", "prolific").books) == 10
```

`after_create` doesn't run on `build`, so `build("author", book_count=3)` has no books. When you need children without a database, or the model takes them as an argument, as a Pydantic model or a dataclass might, build them in a lazy attribute instead:

```python
from factory_bot import build, build_list, f, factory, sequence, transient


@factory(dict)
def line_item():
    f.sku = sequence(lambda n: f"SKU-{n}")


@factory(dict)
def invoice():
    f.item_count = transient(2)
    f.items = lambda item_count: build_list("line_item", item_count)


assert len(build("invoice", item_count=5)["items"]) == 5
```

### Django many-to-many

Django won't take a many-to-many field in the constructor, and can't set one until the row has a primary key. Declare it as a transient, so it never reaches the constructor, and set it after the save:

<!-- skip-doctest -->
```python
from blog.models import Article, Tag

from factory_bot import (
    after_create,
    create,
    create_list,
    f,
    factory,
    sequence,
    transient,
)


@factory(Tag)
def tag():
    f.name = sequence(lambda n: f"tag{n}")


@factory(Article)
def article():
    f.title = "Hello"
    f.tags = transient(())

    @after_create
    def add_tags(article, tags):
        article.tags.set(tags)


article = create("article", tags=[create("tag"), create("tag")])
assert article.tags.count() == 2
```

### Passwords

Take the plain password as a transient and hash it in a lazy attribute. The hash is part of the row's first INSERT, `build` gets it too, and the test still knows the password to log in with.

<!-- skip-doctest -->
```python
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User

from factory_bot import create, f, factory, sequence, transient


@factory(User)
def user():
    f.username = sequence(lambda n: f"user{n}")
    f.raw_password = transient("correct horse battery staple")
    f.password = lambda raw_password: make_password(raw_password)


user = create("user", raw_password="hunter2")
assert user.check_password("hunter2")
```

Django's real hashers are slow on purpose, and that adds up across thousands of test users. In your test settings, use a fast one:

<!-- skip-doctest -->
```python
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
```

### A unique slug derived from another field

A transient sequence gives you the number without putting it on the model, and a lambda combines it with the title:

```python
import re

from factory_bot import build, f, factory, sequence, transient


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@factory(dict)
def page():
    f.title = "Hello, World"
    f.n = transient(sequence(lambda n: n))
    f.slug = lambda title, n: f"{slugify(title)}-{n}"


assert build("page")["slug"] == "hello-world-1"
assert build("page", title="About us")["slug"] == "about-us-2"
```

### SQLAlchemy fixtures

Point `create` at the test's session, inside a transaction that's rolled back afterwards. `persist_with` adds each object and flushes, so ids and foreign keys are filled in, but it never commits. This is SQLAlchemy's own recipe for joining a session to an external transaction, plus two lines for the hook.

<!-- skip-doctest -->
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from factory_bot import to_create
from factory_bot.sqlalchemy import persist_with
from myapp.models import Base


@pytest.fixture(scope="session")
def engine():
    engine = create_engine("sqlite://")  # your test database
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        to_create(persist_with(session))
        yield session
        # The hook is global: don't leave it pointing at a closed session.
        to_create(None)
        session.close()
        transaction.rollback()
```

A test asks for `session` and creates away; associations are flushed before the rows that point at them. `persist_with` also takes a `scoped_session`. Resetting the hook on teardown matters: skip it, and a later test that forgets the fixture writes into this test's closed session.

With `MappedAsDataclass` models, a field declared `init=False` isn't a constructor argument, so a factory can't set it. Set it in an `after_build` callback instead. Without the fixture, `create` falls back to `obj.save()`, which SQLAlchemy models don't have, so a test that forgot it fails loudly.


## Error messages

Every `FactoryError` names the factory involved, and most suggest the fix. The ones you'll meet:

- `No factory named 'usr'. Did you mean 'user'?`

  A typo, or the module that defines the factory was never imported. See [Organizing factories](#organizing-factories).

- `Factory 'user' has no trait 'admn'. Did you mean 'admin'? Traits: admin`

  The list includes the traits a child inherits from its parents.

- `Factory 'user': 'email' depends on 'frist_name', which is not defined. Did you mean 'first_name'? (factories.py:15)`

  A lazy attribute or callback has a parameter that no attribute matches, and the location is the callable's first line. If the parameter was meant to be optional, give it a default.

- `Factory 'account': circular dependency: slug -> url -> slug`

  Attributes that depend on each other. `name -> name` means a callable takes its own attribute as a parameter, as in `f.name = lambda name: name.title()`. To adjust a value after it's worked out, use a callback.

- `Factory 'contact': can't read f.first_name: f only declares attributes. To use another attribute, take it as a parameter: lambda first_name: ...`

  See [`f` is write-only](#f-is-write-only).

- `f.seen = ... only works inside a @factory body`

  `f` was assigned outside a body, or inside a lambda, which runs at build time when no body is running.

- `@factory needs a model: write @factory(User) or @factory(dict) above def guest`

  A bare `@factory` at top level. Bare `@factory` only declares a child, inside another factory.

- `Factory 'user' is already defined (/app/tests/factories.py:12). To redefine it, e.g. in a REPL or after a reload, call clear_factories() first.`

  Two factories share a name, or one definition ran twice: from a fixture, a reloaded module, or a factories module imported under two names. The location is the first definition. In a REPL or after a reload, call `clear_factories()` first.

- `Factory 'member': @factory def moderator must be directly inside the factory, not inside trait 'admin'`

  Child factories and traits belong in a factory body, not in a trait.

- `def member(f) takes no parameters: drop the parameter and import f (from factory_bot import f), and write @trait instead of @f.trait`

  A body written for an earlier release.

- `Factory 'post': 'author' is an association to 'usr', which is not a factory. Did you mean 'user'?`

  Checked at build time, so an association's factory may be defined after the one that uses it.

- `Factory 'user': can't create a dict: it has no save(). Give it a save() method, or set a global hook with to_create(fn).`

  `create` needs to know how to save. Django models have `save()`; for SQLAlchemy, use `persist_with`. If this appears in a test that should have a database, the fixture that sets the hook didn't run.

- `Factory 'user': sequence() takes a function of the counter, e.g. sequence(lambda n: f"user{n}"), not 'user'`

  `sequence` wants a function of the number, not a value.

- `persist_with() takes a Session, not a factory of them. Pass the test's session, e.g. persist_with(session).`

  You passed a `sessionmaker`, or something else that isn't a session.

Errors from the model itself, like a `TypeError` for an unexpected keyword argument or a validation error, come through unchanged. They usually mean an override or attribute the model doesn't accept.


## API at a glance

Defining:

| | |
|---|---|
| `@factory(Model)` | Register a factory named after the function. Nested in a factory, `@factory` declares a child, and `@factory(Model)` a child with its own model. |
| `@trait` | A named set of attributes inside a factory. |
| `f.name = value` | Declare an attribute; see [the value rule](#the-value-rule). |
| `sequence(fn)` | `fn(n)` for n = 1, 2, 3... |
| `association("name", *traits, **overrides)` | Another factory's object. |
| `transient(value)` | An input that never reaches the model. |
| `@after_build`, `@after_create` | Callbacks: `fn(obj, **dependencies)`. |
| `to_create(fn)` | The global save hook; `to_create(None)` restores `obj.save()`. |

Using, each taking `(name, *traits, **overrides)`:

| | |
|---|---|
| `build`, `create`, `attributes_for` | One object, one saved object, or one dict. |
| `build_list(name, n, ...)`, `create_list(name, n, ...)` | A list of `n`. |

Housekeeping: `fake` (a shared `Faker`), `seed(value)`, `reset_sequences()`, `clear_factories()`, `FactoryError`, and `factory_bot.sqlalchemy.persist_with(session)`.


## Type checkers

- `build` and friends return `Any`, so annotate when you want your type checker's help: `user: User = build("user")`.
- mypy `--strict` wants a return type on every function, factory bodies included: `def user() -> None:`.
- A lambda's injected parameters have no types, which pyright's strict mode reports. Where that matters, use an annotated `def` instead; it's injected the same way:

```python
from factory_bot import build, build_list, f, factory, transient


@factory(dict)
def receipt_line():
    f.amount = 1


def receipt_lines(line_count: int) -> list[dict[str, int]]:
    return build_list("receipt_line", line_count)


@factory(dict)
def receipt():
    f.line_count = transient(2)
    f.lines = receipt_lines


assert len(build("receipt")["lines"]) == 2
```
