# factory_bot

Generate realistic test data with ease.

Describe your test data once, and every test can ask for it: `build(user)`, `create(user, "admin", first_name="Jane")`, `build_list(post, 3)`. Each test spells out only the fields it cares about, and the factory fills in the rest, with believable fake values from [Faker](https://faker.readthedocs.io) when you ask for them. It works with anything that takes keyword arguments: plain classes, dataclasses, dicts, Django and SQLAlchemy models. Under pytest, fake data is reseeded for every test, so a test gets the same names and emails whether it runs alone, in the suite, or in a different order.

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

A factory is a plain function that assigns attributes to `f`: no classes, no `Meta`. Its body runs once and records what each attribute should be; every `build` makes a fresh object from that record. Overrides like `first_name="Jane"` win, and attributes that depend on them, like `email`, follow along.

`@factory` returns the factory itself, so `build(user)` is typed as a `User`. Its name works too: `build("user")`.


## Tour

### Dependencies by name

A callable is called on every build, and each parameter is filled with the attribute of the same name. Declaration order doesn't matter.

```python
@factory(dict)
def account():
    f.name = "Ann Lee"
    f.slug = lambda name: name.lower().replace(" ", "-")
    f.url = lambda slug: f"https://example.com/{slug}"


assert build(account)["url"] == "https://example.com/ann-lee"
assert build(account, name="Bea Kim")["url"] == "https://example.com/bea-kim"
```

A typo in a parameter name tells you where it is: `Factory 'account': 'url' depends on 'slgu', which is not defined. Did you mean 'slug'? (factories.py:5)`.

### Transients and callbacks

A transient is an input the model never sees. Callbacks get the built object first, then any attributes they name, transients included.

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

`@after_create` runs after the save. A transient count plus an `@after_create` that calls `create_list` is how you make an author with three books: see the [has-many recipe](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#has-many).

### The same data alone or in the suite

The pytest plugin is on as soon as factory_bot is installed. Before each test it reseeds `fake` from the run's seed and the test's id, so a test's fake data doesn't depend on what ran before it. The seed is in the header:

```
factory_bot: seed=0
```

With [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), its seed drives this one: each run gets new data, and `--randomly-seed=N` replays a run's.

Sequences keep counting across tests, so suites that keep rows between tests don't collide on unique columns. If every test rolls back, restart them per test:

```toml
[tool.pytest.ini_options]
factory_bot_reset_sequences = true
```

To turn the plugin off, run `pytest -p no:factory_bot`.

### Sequences

`sequence` counts up from 1, one step per build. Its function gets the number first, then any attributes it names.

```python
@factory(dict)
def page():
    f.title = "Hello World"
    f.slug = sequence(lambda n, title: f"{title.lower().replace(' ', '-')}-{n}")


assert build(page)["slug"] == "hello-world-1"
assert build(page, title="About")["slug"] == "about-2"
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

### Child factories

A bare `@factory` nested in another declares a child. It inherits the parent's model, attributes, traits, sequences and callbacks, and changes what it needs. Nest `@factory(OtherModel)` to switch model too.

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

A child is reached by its name: `build("moderator")`.

### Associations

`association` gives an attribute another factory's object, with traits and overrides of its own. It follows the parent's strategy: `build` builds it, and `create` creates it first, so it's saved before the row that points at it.

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
    f.author = association(author, "famous", name="Frank")


assert build(book)["author"] == {"name": "Frank", "followers": 1_000_000}
assert build(book, author_id=7) == {"title": "Dune", "author_id": 7}
```

Pass your own object with `author=`, or pass `author_id=` to skip making one.

### Strategies

Every strategy takes traits and overrides the same way.

```python
from factory_bot import attributes_for, build_list, create_list

build(user)  # an object, not saved
create(user)  # built, then saved
attributes_for(user)  # a dict: no object, no callbacks
build_list(user, 3, "admin")  # three users; create_list saves each
```

`attributes_for` leaves out transients, and associations you didn't pass. Values stay Python objects, so serialize them yourself before sending JSON.

### Persistence

`create` builds, then saves: `obj.save()` by default, which is all a Django model needs. For anything else, call `persist_with` with a function, or with a SQLAlchemy session, which gets each object added and flushed, never committed. `persist_with(None)` puts `obj.save()` back.

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

The setting is global. The pytest plugin puts it back after each test, so a fixture can call `persist_with(session)` without cleaning up. The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md#sqlalchemy-fixtures) has the full SQLAlchemy fixture.

### Faker

`fake` is a shared [Faker](https://faker.readthedocs.io) instance, so every Faker provider works. Assign the method without calling it and you get a new value on every build; for arguments, use a lambda. Calling it in the body would freeze one value for every build, so that's an error.

```python
from factory_bot import fake, seed


@factory(dict)
def profile():
    f.name = fake.name
    f.age = lambda: fake.random_int(min=18, max=90)


seed(1234)
first = build(profile)
seed(1234)
assert build(profile) == first
```

`seed(value)` makes the data reproducible outside pytest.

### Checking every factory

`lint()` builds every factory once, and once with each trait, then reports every failure together, each as a call you can paste into a test.

```python
from factory_bot import lint


def test_factories():
    lint()
```


## Learn more

The [guide](https://github.com/dpep/py_factory_bot/blob/main/docs/guide.md) covers the value rule, the gotchas, associations in depth, organizing factories, test isolation, type checkers, recipes, and what each error message means.

Inspired by thoughtbot's [factory_bot](https://github.com/thoughtbot/factory_bot) for Ruby.

----
[![installs](https://img.shields.io/pypi/dm/factory_bot?label=installs)](https://pypi.org/project/factory_bot)
