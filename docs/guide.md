# factory_bot guide

The [README](https://github.com/dpep/py_factory_bot/blob/main/README.md) gets you to a first green test. This is the manual.

- [How a factory works](#how-a-factory-works)
- [The value rule](#the-value-rule)
- [Declaring attributes](#declaring-attributes)
- [Child factories](#child-factories)
- [Associations](#associations)
- [Strategies](#strategies)
- [Saving](#saving)
- [Faker](#faker)
- [Gotchas](#gotchas)
- [Organizing factories](#organizing-factories)
- [Test isolation](#test-isolation)
- [Type checkers](#type-checkers)
- [Recipes](#recipes)
- [Error messages](#error-messages)
- [API at a glance](#api-at-a-glance)


## How a factory works

A factory body is a recipe card, not a meal. It runs once, when Python reaches the `@factory` line, and writes down what each attribute should be. Every `build` cooks a fresh object from that card: it works out each attribute, then calls the model with them as keyword arguments.

```python
from factory_bot import build, f, factory, sequence


@factory(dict)
def user():
    f.name = "Ann"
    f.username = sequence(lambda n: f"user{n}")


assert build(user) == {"name": "Ann", "username": "user1"}
assert build("user", name="Bea") == {"name": "Bea", "username": "user2"}
```

The model is anything that takes keyword arguments: a class, a dataclass, `dict`, a Django or SQLAlchemy model, a plain function. `@factory` returns the factory; its name works anywhere the factory does, and names are global.

When several places set the same attribute, the most specific wins: overrides passed to `build`, then traits (the last listed wins), then a child factory, then its parent. An override may also name an attribute the factory never declared; it goes straight to the model.


## The value rule

- **Calling:** functions (defs, lambdas, methods, builtins like `datetime.now`, `functools.partial`) are called on every build, with each parameter that has no default filled from the attribute of the same name. Every other object is stored, classes, `Mock()` and callable instances included.
- **Copying:** lists, dicts, sets and tuples written in a body are copied per build, nested ones too. Anything you pass at build time is used exactly as given, and never called.
- **Markers:** a `sequence()`, `association()` or `transient()` works only as an attribute's whole value, never returned from a function or inside a container. An override can be a marker too.

```python
from enum import Enum
from unittest.mock import Mock

from factory_bot import fake


class Status(Enum):
    ACTIVE = 1


client = Mock()


@factory(dict)
def person():
    f.first_name = fake.first_name  # a method: called per build
    f.email = lambda first_name: f"{first_name}@example.com".lower()
    f.username = lambda first_name: first_name.lower()  # sees the same first_name
    f.status = Status  # a class: stored
    f.client = client  # not a function: stored
    f.tags = ["new"]  # copied per build


someone = build(person)
assert someone["email"] == f"{someone['username']}@example.com"
assert someone["status"] is Status and someone["client"] is client
```

Each attribute is worked out at most once per build, so everything that depends on it sees the same value.


## Declaring attributes

**Sequences** count from 1, one step per build. The function gets the number first, then any attributes it names. Each sequence keeps its own count, an override doesn't use one up, and `reset_sequences()` restarts them all.

```python
@factory(dict)
def page():
    f.title = "Hello World"
    f.slug = sequence(lambda n, title: f"{title.lower().replace(' ', '-')}-{n}")


assert build(page)["slug"] == "hello-world-1"
assert build(page, title="About")["slug"] == "about-2"
```

**Traits** are named bundles of attributes, applied in the order listed.

```python
from datetime import datetime

from factory_bot import trait


@factory(dict)
def post():
    f.status = "draft"

    @trait
    def published():
        f.status = "published"
        f.published_at = datetime.now

    @trait
    def pinned():
        f.pinned = True


assert build(post, "published", "pinned")["status"] == "published"
assert build(post, "published", status="archived")["status"] == "archived"
```

**Transients** are inputs the model never sees. **Callbacks** get the object first, then any attributes they name, transients included. `@after_build` runs after the model is built; `@after_create` after it's saved.

```python
from factory_bot import after_build, transient


@factory(dict)
def badge():
    f.label = "new"
    f.loud = transient(False)

    @after_build
    def maybe_shout(badge, loud):
        if loud:
            badge["label"] = badge["label"].upper()


assert build(badge) == {"label": "new"}
assert build(badge, loud=True) == {"label": "NEW"}
```

Callbacks run parent first, then the child, then each trait in the order listed.


## Child factories

A child inherits its parent's model, attributes, traits, sequences and callbacks, and changes what it needs. Declare it with `parent=`, or nest a bare `@factory` in the parent's body as shorthand:

```python
@factory(dict)
def member():
    f.name = "Ann"
    f.role = "member"

    @factory
    def guest():
        f.role = "guest"


@factory(parent=member)
def moderator():
    f.role = "moderator"


assert build(moderator) == {"name": "Ann", "role": "moderator"}
assert build("guest") == {"name": "Ann", "role": "guest"}
```

`@factory(OtherModel, parent=member)` switches model too. A `parent=` child is a module-level handle you can import and type-check; a nested one is reached by its name.


## Associations

`association(factory, *traits, **overrides)` makes another factory's object with the parent's strategy: `create` creates it first, so it's saved before the row that points at it, and `build` and `attributes_for` build it.

```python
from dataclasses import dataclass

from factory_bot import association, create


@dataclass
class Account:
    plan: str

    def save(self):
        pass


@dataclass
class Task:
    title: str
    account: Account

    def save(self):
        pass


@factory(Account)
def account():
    f.plan = "free"


@factory(Task)
def task():
    f.title = "Write docs"
    f.account = association(account)


@dataclass
class Workspace:
    account: Account
    task: Task
    items: list

    def save(self):
        pass


@factory(Workspace)
def workspace():
    f.account = association(account, plan="pro")
    f.task = lambda account: association(task, account=account)
    f.item_count = transient(2)
    f.items = lambda item_count: [association(task) for _ in range(item_count)]


w = create(workspace)
assert w.task.account is w.account
assert len(w.items) == 2
```

`association()` called during a build, from a lambda or a callback, simply builds or creates with the parent's strategy. That's how an association takes overrides from other attributes (`task` above), and how the parent gets a list of them (`items`).

To replace one at build time:

- `account=acme` uses your object.
- `account=association(account, plan="pro")` makes one your way.
- `account_id=7` skips the association and passes `account_id=7` to the model. Anything that depends on `account` then raises. This applies only to an attribute declared as `association(...)`, and assumes the foreign key is named `<association>_id`: always true in Django, a convention in SQLAlchemy.
- `account=None` makes none.


## Strategies

| | returns | `after_build` | saved | `after_create` | associations |
|---|---|---|---|---|---|
| `build` | the object | runs | no | no | built |
| `create` | the object | runs | yes | runs | created |
| `attributes_for` | a dict | no | no | no | left out unless you pass one |

`build_list(factory, n, ...)` and `create_list(factory, n, ...)` make `n`, with the same traits and overrides. Every strategy takes traits and overrides the same way. Transients never appear in a result.

`attributes_for` returns Python objects: a `date` stays a `date`. It suits a form or a constructor, not JSON.


## Saving

`create` saves with `obj.save()`, unless you call `persist_with`:

- `persist_with(fn)` calls `fn(obj)`.
- `persist_with(session)` adds each object to a SQLAlchemy `Session` or `scoped_session` and flushes, never commits.
- `persist_with(None)` goes back to `obj.save()`.

The setting is global. Under pytest, one made in a test or fixture is undone when that test or fixture ends.

```python
from factory_bot import persist_with

saved = []
persist_with(saved.append)


@factory(dict)
def event():
    f.name = "launch"


create(event)
assert saved == [{"name": "launch"}]
persist_with(None)
```


## Faker

`fake` is a shared [Faker](https://faker.readthedocs.io) instance. Assign a method without calling it, and you get a new value every build; for arguments, use a lambda. Calling one in a body is an error, because it would freeze one value for every build.

```python
from factory_bot import seed


@factory(dict)
def profile():
    f.name = fake.name
    f.age = lambda: fake.random_int(min=18, max=90)


seed(1234)
first = build(profile)
seed(1234)
assert build(profile) == first
```

`seed(value)` makes the data reproducible outside pytest; it also clears `fake.unique`. Under pytest, the plugin seeds for you; a test or fixture that calls `seed()` itself keeps that seed for the rest of the test. Use `factory_bot.seed`, not `Faker.seed()`: that seeds Faker's shared generator, which `fake` stops using once seeded. `fake` is the only randomness it seeds, so prefer `fake.random_element(...)` to `random.choice(...)`.


## Gotchas

- **A body runs once.** `f.at = datetime.now()` is frozen at import; `f.at = datetime.now` is called per build. Calling `fake.x()`, `build()` or `create()` in a body is an error for this reason.
- **`f` is write-only.** To use another attribute, take it as a parameter: `f.email = lambda first_name: ...`, not `f.first_name + ...`.
- **Objects are shared.** Only containers written in a body are copied. A model instance in a body is the same object in every build; build it in a lambda for a fresh one.
- **Keyword names.** `setattr(f, "from", "ann@example.com")` declares an attribute named like a Python keyword, but no lambda can take it as a parameter.


## Organizing factories

Put your factories in `tests/factories.py`, and import it once from `tests/conftest.py`. The import registers them all before any test runs.

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

Tests then use `build("user")`, or `from factories import user` for types.

`import factories` works with pytest's default import mode when `tests/` has no `__init__.py`. If `tests/` is a package, write `from . import factories`. Under `--import-mode=importlib`, add `pythonpath = ["tests"]` to your pytest config.

Define factories at module level, not in tests or fixtures, since names are global. In a REPL, or before reloading the module, call `clear_factories()`.


## Test isolation

The pytest plugin:

- **Reseeds `fake`** for every test and every fixture, at any scope, from the run's seed and its id. Each gets the same fake data alone, in the suite, in any order or under pytest-xdist. With pytest-randomly, each run picks a new seed, and `--randomly-seed=N` replays it.
- **Undoes `persist_with`** when the test or fixture that called it ends.
- **Leaves sequences counting** across tests, unless you ask. Restarting them makes two tests both create `user1`, which collides when rows survive between tests. If every test rolls back, turn it on:

  ```toml
  [tool.pytest.ini_options]
  factory_bot_reset_sequences = true
  ```

  The header shows the setting: `factory_bot: seed=0, reset_sequences=off`. Either way, don't assert on a sequence value; pass the value you assert on as an override.

Database rows are your test framework's job: Django's `TestCase` and the SQLAlchemy fixture below roll back.


## Type checkers

`@factory(User)` returns a `Factory[User]`, so `build(user)`, `create(user)` and `build_list(user, 3)` are typed. A name gives `Any`.

```python
@dataclass
class Member:
    name: str


@factory(Member)
def typed_member():
    f.name = "Ann"


m: Member = build(typed_member)
```

- Use a name where no handle is in reach: a nested child, or a factory defined later in the file.
- A pytest fixture named `user` shadows an imported `user` factory. Import the module and write `build(factories.user)`.
- mypy `--strict` wants a return type on bodies: `def user() -> None:`.
- pyright strict reports a lambda's injected parameters as untyped. Where that matters, use an annotated `def`, injected the same way.


## Recipes

### Has-many

When each child row holds the key to its parent, the parent must be saved first. A transient count and an `after_create` callback create the children afterwards:

```python
from dataclasses import field

from factory_bot import after_create, create_list


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
        self.author.books.append(self)  # stands in for the ORM's back-reference


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
        create_list(book, book_count, author=author)

    @trait
    def prolific():
        f.book_count = 10


assert len(create(author, book_count=3).books) == 3
assert len(create(author, "prolific").books) == 10
```

`after_create` doesn't run on `build`, so a built author has no books. When the parent holds the list instead, call `association()` in a lambda, as `items` does in [Associations](#associations).

### Django many-to-many

Django won't take a many-to-many field in the constructor, or set one before the row has a primary key. Make it a transient, and set it after the save:

<!-- skip-doctest -->
```python
from blog.models import Article, Tag

from factory_bot import after_create, create, f, factory, sequence, transient


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


article_ = create(article, tags=[create(tag), create(tag)])
assert article_.tags.count() == 2
```

### Django passwords

Take the plain password as a transient and hash it in a lambda. The hash goes into the first INSERT, `build` gets it too, and the test still knows the password.

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


assert create(user, raw_password="hunter2").check_password("hunter2")
```

Django's hashers are slow on purpose. In test settings, use a fast one: `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]`.

### SQLAlchemy fixtures

This fixture joins the test's session to an outer transaction that's rolled back, SQLAlchemy's own recipe, plus one line:

<!-- skip-doctest -->
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from factory_bot import persist_with
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
        persist_with(session)  # undone when the fixture ends
        yield session
        session.close()
        transaction.rollback()
```

With `MappedAsDataclass` models, a field declared `init=False` isn't a constructor argument, so set it in an `after_build` callback.

### Checking every factory

`lint()` builds every factory once, then once with each of its traits, and raises one error listing every call that failed:

```
FactoryError: lint: 3 of 5 builds failed:
  build('guest', 'vip'): ZeroDivisionError: division by zero
  build('ghost'): FactoryError: Factory 'ghost': 'name' depends on 'nmae', which is not defined. Did you mean 'name'? (factories.py:20)
  build('ghost', 'vip'): FactoryError: Factory 'ghost': 'name' depends on 'nmae', which is not defined. Did you mean 'name'? (factories.py:20)
```

Its builds are real: they use up sequence numbers, and `strategy="create"` saves rows. Run it in a test, inside your rollback:

<!-- skip-doctest -->
```python
# tests/test_factories.py
from factory_bot import lint


def test_factories_build():
    lint()


def test_factories_create(session):  # or @pytest.mark.django_db
    lint("user", "post", strategy="create")  # those with a table behind them
```


## Error messages

Every `FactoryError` names the factory it happened in, and most say how to fix it. An exception from your model or your functions keeps its type and gains notes naming the factory, the attribute and its line. These need more context than the message has room for:

- `Factory 'book': 'byline' depends on 'author', which isn't made because author_id= was given. Pass author= as well.`

  `author_id=` skips the `author` association, so nothing that needs the author object can run. Pass both, or neither.

- `Factory 'user' is already defined (<full path>/tests/factories.py:4). To redefine it, e.g. in a REPL or after a reload, call clear_factories() first.`

  If the path is the very line being defined, the module was imported twice, under two names (`factories` and `tests.factories`). Fix the import, not the factory.

- `Factory 'person': circular dependency: name -> name`

  A lambda takes its own attribute as a parameter: `f.name = lambda name: name.title()`. To adjust a value after it's worked out, use a callback.

- `Factory 'account': can't create a dict: it has no save(). Give it a save() method, or call persist_with() with a function or a SQLAlchemy session.`

  In a test that should have a database, the fixture that calls `persist_with` didn't run.

- `'team__name': deep overrides aren't supported. Override the association instead: team=association("team", name=...)` (a note on the model's `TypeError`)

  There's no `__` syntax. Pass a whole association with its own overrides.

- `Factory 'ticket': <sequence (factories.py:59)> was never evaluated: a sequence(), association() or transient() works only as an attribute's whole value, never returned from a function or inside a container.`

  Assign the marker itself, `f.code = sequence(...)`. For a list of associations, call `association()` in a lambda: `lambda: [association(user)]`.


## API at a glance

| | |
|---|---|
| `@factory(Model)`, `@factory(parent=f)`, `@factory(Model, parent=f)` | Register a factory named after the function, returning a `Factory`. Nested bare `@factory` is a child of the enclosing factory. |
| `@trait` | A named set of attributes inside a factory. |
| `f.name = value` | Declare an attribute: see [the value rule](#the-value-rule). |
| `sequence(fn)` | `fn(n, **dependencies)` for n = 1, 2, 3... |
| `association(factory, *traits, **overrides)` | Another factory's object. |
| `transient(value)` | An input that never reaches the model. |
| `@after_build`, `@after_create` | Callbacks: `fn(obj, **dependencies)`. |
| `build`, `create`, `attributes_for` `(factory, *traits, **overrides)` | One object, one saved object, or one dict. `factory` is a `Factory` or its name. |
| `build_list`, `create_list` `(factory, n, *traits, **overrides)` | A list of `n`. |
| `persist_with(fn \| session \| None)` | How `create` saves. |
| `lint(*factories, strategy="build")` | Build every factory and trait; report every failure. |
| `fake`, `seed(value)` | The shared `Faker`, and its seed. |
| `reset_sequences()`, `clear_factories()` | Restart every sequence; forget every factory. |
