# factory_bot

Generate realistic test data with ease.

Describe your test data once, and every test can ask for it by name: `build("user")`, `create("user", "admin", first_name="Jane")`, `build_list("post", 3)`. Each test spells out only the fields it cares about, and the factory fills in the rest, with believable fake values from [Faker](https://faker.readthedocs.io) when you ask for them. It works with anything that takes keyword arguments: plain classes, dataclasses, dicts, Django and SQLAlchemy models. Under pytest, fake data is reseeded for every test, so a test gets the same names and emails whether it runs alone, in the suite, or in a different order.

Early development: the API is still settling.


## Install

```
pip install factory_bot
```

Python 3.11 or later.


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


build("user")
# User(first_name='Diane', last_name='Butler', email='Diane.Butler@example.com', username='user1', admin=False)

create("user", "admin", first_name="Jane")
# User(first_name='Jane', last_name='Turner', email='Jane.Turner@example.com', username='user2', admin=True)
```

A factory is a function that assigns attributes to `f`. Its body runs once, when it's defined, and records what each attribute should be; every `build` then makes a fresh object from that record. Overrides, like `first_name="Jane"`, win over everything, and attributes that depend on them (`email`) follow along.


## Tour

### Lazy attributes and dependencies

A static value is used as-is, and so is a class. Any other callable is called on every build, and its parameters are filled with the other attributes of the same name, so one attribute can depend on another.

```python
@factory(dict)
def account():
    f.name = "Ann Lee"
    f.slug = lambda name: name.lower().replace(" ", "-")
    f.url = lambda slug: f"https://example.com/{slug}"


assert build("account")["url"] == "https://example.com/ann-lee"
assert build("account", name="Bea Kim")["url"] == "https://example.com/bea-kim"
```

Only parameters without defaults are filled, and order of declaration doesn't matter. The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#the-value-rule) has the full rule.

### Sequences

For values that must be unique, `sequence` counts up from 1, one step per build.

```python
@factory(dict)
def ticket():
    f.code = sequence(lambda n: f"T-{n:04}")


assert build("ticket") == {"code": "T-0001"}
assert build("ticket") == {"code": "T-0002"}
```

Each sequence keeps its own count, an override doesn't use up a number, and `reset_sequences()` starts every count over.

### Traits

A trait is a named bundle of attributes you switch on per build. Traits apply in the order you list them, later ones win, and overrides beat them all.

```python
from datetime import datetime


@factory(dict)
def post():
    f.title = "Hello"
    f.status = "draft"
    f.published_at = None

    @trait
    def published():
        f.status = "published"
        f.published_at = datetime.now

    @trait
    def pinned():
        f.pinned = True


assert build("post", "published", "pinned")["status"] == "published"
assert build("post", "published", status="archived")["status"] == "archived"
```

### Child factories

A bare `@factory` nested in another declares a child: it inherits the parent's model, attributes, traits, sequences and callbacks, and changes what it needs. Nest `@factory(OtherModel)` to switch model too.

```python
@factory(dict)
def member():
    f.name = "Ann"
    f.role = "member"

    @factory
    def moderator():
        f.role = "moderator"


assert build("moderator") == {"name": "Ann", "role": "moderator"}
```

Children are registered under their own name, so `build("moderator")`, not `build("member.moderator")`.

### Associations

`association` gives an attribute another factory's object, with traits and overrides of its own. It follows the parent's strategy: `build` builds it, `create` creates it first, so it's saved before the row that points at it.

```python
from factory_bot import association


@factory(dict)
def author():
    f.name = "Ann"

    @trait
    def famous():
        f.followers = 1_000_000


@factory(dict)
def book():
    f.title = "Dune"
    f.author = association("author", "famous", name="Frank")


assert build("book") == {
    "title": "Dune",
    "author": {"name": "Frank", "followers": 1_000_000},
}
```

Pass your own to skip it: `build("book", author=frank)`.

### Transients

A transient is an input other attributes can depend on that never reaches the model.

```python
from factory_bot import transient


@factory(dict)
def greeting():
    f.loud = transient(False)
    f.text = lambda loud: "HELLO" if loud else "hello"


assert build("greeting") == {"text": "hello"}
assert build("greeting", loud=True) == {"text": "HELLO"}
```

### Callbacks

`@after_build` runs on the built object; `@after_create` runs after it's saved. A callback gets the object first, then any attributes it names, transients included.

```python
from factory_bot import after_build


@factory(dict)
def badge():
    f.label = "new"
    f.shout = transient(False)

    @after_build
    def maybe_shout(badge, shout):
        if shout:
            badge["label"] = badge["label"].upper()


assert build("badge", shout=True) == {"label": "NEW"}
```

Callbacks run in definition order: parent, then child, then traits.

### Strategies

Every strategy takes traits and overrides the same way.

```python
from factory_bot import attributes_for, build_list, create_list

build("user")  # an object, not saved
create("user")  # built, then saved
attributes_for("user")  # a dict of attributes: no object, no callbacks, no associations
build_list("user", 3, "admin")  # three users; create_list saves each
```

`attributes_for` leaves out transients and associations, which makes it handy for a form or a constructor. The values are Python objects (dates stay dates), so serialize them yourself before sending JSON.

### Persistence

`create` builds the object, then saves it. By default that means calling `obj.save()`, which is all a Django model needs: there's nothing to configure.

For anything else, set a hook with `persist_with(fn)`. At top level it applies to every factory, across the whole process; `persist_with(None)` puts `obj.save()` back.

```python
from factory_bot import persist_with

saved = []
persist_with(saved.append)


@factory(dict)
def event():
    f.name = "launch"


create("event")
assert saved == [{"name": "launch"}]
persist_with(None)
```

For SQLAlchemy, `persist_with(session)` adds each created object to the session and flushes, so ids and foreign keys are set but nothing is committed: your test's transaction still decides.

<!-- skip-doctest -->
```python
import factory_bot.sqlalchemy

persist_with(factory_bot.sqlalchemy.persist_with(session))
```

The hook is global, so reset it with `persist_with(None)` when the test's session goes away, or a later test writes into a closed session. The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#sqlalchemy-fixtures) has a fixture that does.

### Faker

`fake` is a shared [Faker](https://faker.readthedocs.io) instance, so every Faker provider works. Assign the method without calling it, and you get a new value on every build. Need arguments? Wrap it in a lambda.

```python
from factory_bot import fake, seed


@factory(dict)
def profile():
    f.name = fake.name
    f.bio = fake.sentence
    f.age = lambda: fake.random_int(min=18, max=90)


seed(1234)
first = build("profile")
seed(1234)
assert build("profile") == first
```

`seed(value)` makes the data reproducible. Under pytest you rarely need it, because the plugin seeds for you.

### pytest

Install factory_bot and its pytest plugin is on. Before each test it reseeds `fake` from the run's seed and the test's id, so a test's fake data is the same alone, in the suite, or in any order, while each test still gets data of its own. The seed is in the header:

```
factory_bot: seed=0
```

With [pytest-randomly](https://github.com/pytest-dev/pytest-randomly) installed, its seed drives this one too: each run gets new data, and `--randomly-seed=N` replays a run's.

Sequences keep counting across tests, so suites that keep rows between tests don't collide on unique columns. If every test rolls back, as with Django's `TestCase`, restart them per test:

```toml
[tool.pytest.ini_options]
factory_bot_reset_sequences = true
```

To turn the plugin off, run `pytest -p no:factory_bot`.


## Learn more

The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md) covers the value rule, the gotchas, organizing factories, test isolation, recipes for has-many, Django many-to-many, passwords, unique slugs and SQLAlchemy fixtures, what each error message means, and tips for type checkers.

Inspired by thoughtbot's [factory_bot](https://github.com/thoughtbot/factory_bot) for Ruby.

----
[![installs](https://img.shields.io/pypi/dm/factory_bot?label=installs)](https://pypi.org/project/factory_bot)
