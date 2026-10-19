from dataclasses import dataclass, field


@dataclass
class User:
    first_name: str = ""
    last_name: str = ""
    email: str | None = None
    username: str = ""
    admin: bool = False
    tags: list = field(default_factory=list)
