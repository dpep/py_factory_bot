factory_bot
======
Test data factories with the ergonomics of Ruby's [factory_bot](https://github.com/thoughtbot/factory_bot).

Early development: the API is still settling.


### Install
```pip install factory_bot```


### Usage
```python
from factory_bot import build, f, factory, fake, sequence, trait

@factory(User)
def user():
    f.first_name = fake.first_name                    # callables run per build
    f.email = lambda first_name: f"{first_name}@example.com".lower()  # dependencies by name
    f.username = sequence(lambda n: f"user{n}")
    f.admin = False

    @trait
    def admin():
        f.admin = True

build("user")
# User(first_name='Dennis', email='dennis@example.com', username='user1', admin=False)

build("user", "admin", first_name="Jane")
# User(first_name='Jane', email='jane@example.com', username='user2', admin=True)
```

----
[![installs](https://img.shields.io/pypi/dm/factory_bot?label=installs)](https://pypi.org/project/factory_bot)
