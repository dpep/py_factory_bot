from dataclasses import dataclass, field


@dataclass
class User:
    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    username: str = ""
    admin: bool = False
    tags: list = field(default_factory=list)
    saved: bool = field(default=False, init=False, compare=False)

    def save(self):
        self.saved = True


@dataclass
class Post:
    title: str = ""
    author: User | None = None
    saved: bool = field(default=False, init=False, compare=False)

    def save(self):
        self.saved = True
