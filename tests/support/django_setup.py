import django
from django.conf import settings
from django.core.management import call_command


def setup():
    """Configure Django once per process with an in-memory sqlite DB; later calls are no-ops."""
    if not settings.configured:
        settings.configure(
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
            INSTALLED_APPS=["support.django_app"],
            DEFAULT_AUTO_FIELD="django.db.models.AutoField",
        )
    django.setup()
    call_command("migrate", run_syncdb=True, verbosity=0)
