# factory_bot guide

The [README](https://github.com/dpep/py_factory_bot/blob/main/README.md) is the tour. This is the manual.

- [How a factory works](#how-a-factory-works)
- [The value rule](#the-value-rule)
- [Gotchas](#gotchas)
- [Strategies and callbacks](#strategies-and-callbacks)
- [Associations](#associations)
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

The model is anything that takes keyword arguments: a class, a dataclass, `dict`, a Django or SQLAlchemy model, a plain function.

`@factory` returns the factory, which you pass to `build`. Its name, `"user"`, works anywhere the factory does. Names are global, so each must be unique.

When several places set the same attribute, the most specific wins:

1. overrides passed to `build(...)`
2. traits, in the order listed (the last one wins)
3. the child factory
4. its parent

An override may also name an attribute the factory never declared; it goes straight to the model.


## The value rule

Each build turns every attribute into a value by one rule:

- **A marker** does its job. `sequence(fn)` calls `fn` with its next number, then any attributes it names. `association(factory, ...)` makes that factory's object. `transient(value)` resolves `value` by this same rule, but keeps it from the model.
- **A class** is stored as-is: `f.status = Status` gives the `Enum` class.
- **Any other callable** is called on every build. Each parameter without a default is filled with the attribute of the same name. Parameters with defaults, `*args` and `**kwargs` are left alone.
- **A list, dict, set or tuple** is copied, nested ones too, so builds never share one.
- **Anything else** is used as-is: every build gets that same object.
- **An override** is a plain value, used as given and never called. An override that's a marker is evaluated like a declaration: `build(user, username=sequence(lambda n: f"guest{n}"))`.

Each attribute is worked out at most once per build, so everything that depends on it sees the same value.

```python
from enum import Enum

from factory_bot import fake


class Status(Enum):
    ACTIVE = 1


@factory(dict)
def person():
    f.first_name = fake.first_name  # called per build
    f.email = lambda first_name: f"{first_name}@example.com".lower()
    f.username = lambda first_name: first_name.lower()  # the same first_name
    f.bio = fake.paragraph  # parameters all have defaults: nothing injected
    f.status = Status  # a class: stored
    f.tags = ["new"]  # copied per build


someone = build(person)
assert someone["email"] == f"{someone['username']}@example.com"
assert someone["status"] is Status
```

A marker only works as an attribute's whole value. Inside a list, or returned from a function, it's an error, because it would reach the model unevaluated. The one exception is `association()` called during a build: see [Associations](#associations).


## Gotchas

### A callable you want stored needs a lambda

Classes are stored, but every other callable is called: a function, a `Mock()`, a bound method. To store one, wrap it:

```python
from unittest.mock import Mock

client = Mock()


@factory(dict)
def service():
    f.client = lambda: client  # f.client = client would store client()


assert build(service)["client"] is client
```

### Bodies run once

Code in a body runs once, at import, not per build. A timestamp or a random choice is frozen into the factory:

```python
import random
from datetime import datetime


@factory(dict)
def visit():
    f.at = datetime.now()  # frozen: the time of import
    f.seen_at = datetime.now  # per build
    f.score = lambda: random.choice([1, 2, 3])  # per build
```

Calling `fake.x()`, `build()` or `create()` in a body is an error for this reason.

### `f` is write-only

`f` records what you assign; there's nothing to read back until a build happens. Take the other attribute as a parameter instead:

```python
@factory(dict)
def contact():
    f.first_name = "Ann"
    f.email = lambda first_name: f"{first_name}@example.com"  # not f.first_name
```

### Other objects are shared

Only builtin containers are copied. A model instance or any other object in a body is the same object in every build. Build it in a lambda for a fresh one: `f.address = lambda: Address(city="Wellington")`.

### Keyword names

An attribute named like a Python keyword can be declared with `setattr(f, "from", "ann@example.com")`, but no lambda can take it as a parameter.


## Strategies and callbacks

| | returns | `after_build` | saved | `after_create` | associations |
|---|---|---|---|---|---|
| `build` | the object | runs | no | no | built |
| `create` | the object | runs | yes | runs | created |
| `attributes_for` | a dict | no | no | no | left out, unless passed |

`build_list` and `create_list` call `build` or `create` once per object, with the same traits and overrides. Transients never appear in a result.

`attributes_for` returns values as Python objects: a `date` stays a `date`, and a nested object stays an object. It's ready for a form or a constructor, not for JSON.

A callback's first parameter is the object, whatever you name it. The rest are filled by name, transients included. Callbacks run parent first, then the child, then each trait in the order listed.

`after_build` also runs on `create`, before the save, so anything that must be saved with the row belongs there. `after_create` never runs on `build`.

`create` saves with `obj.save()`, or with whatever `persist_with` set: a function called with each object, or a SQLAlchemy session that gets `add(obj)` and `flush()`, never a commit. The setting is global, for every thread.


## Associations

`association(factory, *traits, **overrides)` makes another factory's object, with the parent's strategy: `create` creates it, and `build` and `attributes_for` build it.

```python
from dataclasses import dataclass

from factory_bot import association, attributes_for, create


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


@dataclass
class Profile:
    account: Account
    task: Task

    def save(self):
        pass


@factory(Account)
def account():
    f.plan = "free"


@factory(Task)
def task():
    f.title = "Write docs"
    f.account = association(account)


@factory(Profile)
def profile():
    f.account = association(account, plan="pro")
    f.task = lambda account: association(task, account=account)


p = create(profile)
assert p.task.account is p.account
```

That last line is the dependent form. Called while a build is running, from a lambda or a callback, `association()` makes the object right away, with the parent's strategy. Use it when an association's overrides depend on another attribute, or for a list: `lambda item_count: [association(item) for _ in range(item_count)]`.

Ways to replace it:

- `build(task, account=acme)` uses your object.
- `build(task, account=association(account, plan="pro"))` makes one your way.
- `build(task, account_id=7)` skips the association and passes `account_id=7` to the model. Anything that depends on `account` then raises. This only applies to an attribute declared as `association(...)`.
- `build(task, account=None)` makes none.

`attributes_for` leaves associations out unless you pass them, but still builds one when another attribute depends on it.

The `_id` rule assumes the foreign key is named `<association>_id`. Django always names it that. In SQLAlchemy it's only a convention: a relationship `author` over a column `writer_id` won't match, so pass `author=` there.

Two associations that make each other forever raise `circular association: book.author -> author.book -> book.author`.


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

Tests then use `build("user")`, or import the factory for types: `from factories import user`.

`import factories` works with pytest's default import mode when `tests/` has no `__init__.py`. If `tests/` is a package, write `from . import factories`. Under `--import-mode=importlib`, add `pythonpath = ["tests"]` to your pytest config.

Define factories at module level, not in tests or fixtures: a factory defined in a fixture is defined again by the next test, and raises `already defined`. In a REPL, or before reloading the module, call `clear_factories()`.


## Test isolation

What the pytest plugin does before and after each test, and what's left to you:

- **`fake` is reseeded** from the run's seed and the test's id, and `fake.unique` is cleared, so a test's fake data doesn't depend on what ran before it. This happens before fixtures run, so function-scoped fixtures get the test's data too. A module- or session-scoped fixture gets the seed of the first test that uses it, so its data can change with which tests run.
- **The `persist_with` setting is restored** after the test, undoing anything the test or its function-scoped fixtures set. A module- or session-scoped fixture that calls it must undo it in its own teardown.
- **Sequences keep counting** across tests: `user1` when a test runs alone can be `user7` in the suite. Restarting them per test would make two tests both create `user1`, which collides when rows survive between tests. If every test rolls back, turn it on:

  ```toml
  [tool.pytest.ini_options]
  factory_bot_reset_sequences = true
  ```

  Either way, don't assert on a sequence value; pass the value you assert on as an override.
- **Database rows** are your test framework's job. Django's `TestCase` and the SQLAlchemy fixture below both roll back.

With pytest-randomly installed, each run picks a new seed; `--randomly-seed=N` (from the header) gets that run's data back.

`fake` is the only randomness the plugin seeds. Prefer `fake.random_element(...)` to `random.choice(...)` in a lambda.


## Type checkers

`@factory(User)` returns a `Factory[User]`, so `build(user)`, `create(user)` and `build_list(user, 3)` are typed. A name, `build("user")`, gives `Any`, as does a child factory, which you can only reach by name.

```python
@dataclass
class Member:
    name: str


@factory(Member)
def member():
    f.name = "Ann"


m: Member = build(member)
```

- **Fixture with the same name.** A pytest fixture called `user` shadows an imported `user` factory. Import the module instead and write `build(factories.user)`; passing the wrong thing raises `Expected a factory or a factory's name`.
- **mypy `--strict`** wants a return type on bodies: `def user() -> None:`.
- **pyright strict** reports a lambda's injected parameters as untyped. Where that matters, use an annotated `def`, injected the same way:

```python
@factory(dict)
def receipt():
    f.line_count = 2

    def total(line_count: int) -> int:
        return line_count * 10

    f.total = total


assert build(receipt)["total"] == 20
```


## Recipes

### Has-many

When each child row points at its parent, create the parent first, then the children, from an `after_create` callback driven by a transient count:

```python
from dataclasses import field

from factory_bot import after_create, create_list, trait, transient


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

`after_create` doesn't run on `build`, so a built author has no books.

When the parent holds its children, as a list field or a relationship you assign, call `association()` in a lambda. It follows the strategy, so it works with `build` too:

```python
@factory(dict)
def line_item():
    f.sku = sequence(lambda n: f"SKU-{n}")


@factory(dict)
def invoice():
    f.item_count = transient(2)
    f.items = lambda item_count: [association(line_item) for _ in range(item_count)]


assert len(build(invoice, item_count=5)["items"]) == 5
```

### Django many-to-many

Django won't take a many-to-many field in the constructor, and can't set one until the row has a primary key. Declare it as a transient, so it never reaches the constructor, and set it after the save:

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

### Passwords

Take the plain password as a transient and hash it in a lambda. The hash goes into the row's first INSERT, `build` gets it too, and the test still knows the password.

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

Django's hashers are slow on purpose. In test settings, use a fast one:

<!-- skip-doctest -->
```python
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
```

### SQLAlchemy fixtures

Point `create` at the test's session, inside a transaction that's rolled back afterwards. This is SQLAlchemy's recipe for joining a session to an outer transaction, plus one line:

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
        persist_with(session)  # the plugin undoes it after the test
        yield session
        session.close()
        transaction.rollback()
```

`create` adds and flushes, so ids and foreign keys are set, but never commits. Associations are flushed before the rows that point at them. `persist_with` also takes a `scoped_session`.

With `MappedAsDataclass` models, a field declared `init=False` isn't a constructor argument, so a factory can't set it; set it in an `after_build` callback.

### Checking every factory

`lint()` builds every factory once, then once with each of its traits, and raises one error listing every call that failed:

```
FactoryError: lint: 3 of 5 builds failed:
  build('guest', 'vip'): ZeroDivisionError: division by zero
  build('ghost'): FactoryError: Factory 'ghost': 'name' depends on 'nmae', which is not defined. Did you mean 'name'? (factories.py:20)
  build('ghost', 'vip'): FactoryError: Factory 'ghost': 'name' depends on 'nmae', which is not defined. Did you mean 'name'? (factories.py:20)
```

Its builds are real: they use up sequence numbers, and `strategy="create"` saves rows. So run it in a test, inside your rollback:

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

A `FactoryError` names the factory it happened in, and most suggest the fix. An exception from your model or your lambdas keeps its type and gains notes naming the factory, the attribute and its line:

```
ZeroDivisionError: division by zero
  note: while building factory 'boom', attribute 'value' (factories.py:292)
```

### When you build

- `No factory named 'usr'. Did you mean 'user'?`

  A typo, or the factories module wasn't imported.

- `Factory 'user' has no trait 'admn'. Did you mean 'admin'? Traits: admin`

  The list includes inherited traits.

- `Expected a factory or a factory's name, not <class 'myapp.models.User'>. If a fixture or variable shadows the factory, use its name or its module: factories.user`

  You passed the model, or a fixture shadowed the factory. See [Type checkers](#type-checkers).

- `Factory 'user': 'email' depends on 'nmae', which is not defined. Did you mean 'name'? (factories.py:25)`

  A lambda, sequence or callback has a parameter no attribute matches. If it's meant to be optional, give it a default.

- `Factory 'account': circular dependency: slug -> url -> slug`

  Attributes that need each other. `name -> name` means a lambda takes its own attribute; adjust a value in a callback instead.

- `Factory 'post': 'author' is an association to 'usr', which is not a factory. Did you mean 'user'?`

  Checked at build time, so the target can be defined after the factory that uses it.

- `Factory 'book': circular association: book.author -> author.book -> book.author`

  Each association makes the other. Pass one in, or set it to `None`.

- `Factory 'book': 'byline' depends on 'author', which isn't made because author_id= was given. Pass author= as well.`

  See [Associations](#associations).

- `Factory 'ticket': <sequence (factories.py:59)> was returned from a function, so it was never evaluated: a sequence(), association() or transient() works only as an attribute's whole value, never returned from a function or inside a container.`

  Assign the marker itself: `f.code = sequence(...)`.

- `Factory 'ticket': <association 'user'> is inside a list, so it was never evaluated: ...`

  For a list of associations, build it in a lambda: `lambda: [association(user)]`.

- `Factory 'account': can't create a dict: it has no save(). Give it a save() method, or call persist_with() with a function or a SQLAlchemy session.`

  `create` doesn't know how to save. If the test should have a database, its fixture didn't run.

- `lint() takes strategy='build' or 'create', not 'attributes_for'`

A model's `TypeError` for an unknown keyword gains a hint:

```
TypeError: User.__init__() got an unexpected keyword argument 'nmae'
  note: while building factory 'member'
  note: 'nmae' is not an attribute of factory 'member'. Did you mean 'name'?
```

Overrides like `team__name=` aren't supported; the note says to pass `team=association("team", name=...)`.

### When you define

- `Factory 'guest': fake.first_name() was called while the factory was being defined, so every build would get the same value. Pass the method instead, without parentheses: fake.first_name (or lambda: fake.first_name(...) for arguments)`
- `Factory 'shelf': build('book') ran while a factory was being defined, so it would run once, at import. Use association('book'), which builds or creates to match the parent, or make it lazy: lambda: build('book')`
- `Factory 'contact': can't read f.first_name: f only declares attributes. To use another attribute, take it as a parameter: lambda first_name: ...`
- `f.name = ... only works inside a @factory body`

  Also raised by `f` assigned in a lambda, which runs at build time.

- `@factory needs a model or a parent: write @factory(User), @factory(dict) or @factory(parent=user) above def guest`

  A bare `@factory` only declares a child, inside another factory.

- `Factory 'guest': model 'User' is not callable`
- `Factory 'user' is already defined (<full path>/tests/factories.py:22). To redefine it, e.g. in a REPL or after a reload, call clear_factories() first.`

  Two factories share a name, or one module ran twice: from a fixture, a reload, or an import under two module names.

- `Factory 'guest': trait 'vip' is already defined (factories.py:135)`
- `def guest(f) takes no parameters: drop the parameter and import f (from factory_bot import f), and write @trait instead of @f.trait`

  A body written for 0.0.1.

- `@factory takes a def, not a lambda: the function's name names the factory`
- `def guest must be a plain function: its body runs once, now`
- `Factory 'guest': @factory def ghost must be directly inside the factory, not inside trait 'vip'`
- `Factory 'guest': @after_build def greet() must take the instance first, then other attributes by name: def greet(guest, ...)`
- `sequence() takes a function of the counter, e.g. sequence(lambda n: f"user{n}"), not 'user'`

### When you set up saving

- `persist_with() takes a session, not a sessionmaker. Pass the test's session, e.g. persist_with(session).`
- `persist_with() takes a function, a SQLAlchemy session, or None to restore obj.save(); got Engine(sqlite://).`
- `Factory 'guest': persist_with() sets the global save hook, so call it outside any factory body, e.g. in a fixture.`


## API at a glance

Defining:

| | |
|---|---|
| `@factory(Model)` | Register a factory named after the function; returns a `Factory[Model]`. Nested in a factory, bare `@factory` declares a child, and `@factory(Model)` a child with its own model. |
| `@trait` | A named set of attributes inside a factory. |
| `f.name = value` | Declare an attribute; see [the value rule](#the-value-rule). |
| `sequence(fn)` | `fn(n, **dependencies)` for n = 1, 2, 3... |
| `association(factory, *traits, **overrides)` | Another factory's object. |
| `transient(value)` | An input that never reaches the model. |
| `@after_build`, `@after_create` | Callbacks: `fn(obj, **dependencies)`. |

Using, where `factory` is a `Factory` or its name:

| | |
|---|---|
| `build`, `create`, `attributes_for` `(factory, *traits, **overrides)` | One object, one saved object, or one dict. |
| `build_list`, `create_list` `(factory, n, *traits, **overrides)` | A list of `n`. |
| `persist_with(fn \| session \| None)` | How `create` saves. |
| `lint(*factories, strategy="build")` | Build every factory and trait; report every failure. |

Housekeeping: `fake` (a shared `Faker`), `seed(value)`, `reset_sequences()`, `clear_factories()`, `Factory`, and `FactoryError`.
