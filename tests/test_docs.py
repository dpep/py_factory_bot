"""Run every ```python block in the README and the guide, so the docs can't rot.

A file's blocks run in order in one module, the way a reader follows along: a later block
may use an earlier block's imports, models and factories. A block that needs setup this
suite doesn't have (a Django project, a live session) can opt out with an
<!-- skip-doctest --> line just above its fence.
"""

import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["README.md", "docs/guide.md"]
BLOCK = re.compile(
    r"^(<!-- skip-doctest -->\n)?```python\n(.*?)^```$", re.MULTILINE | re.DOTALL
)


def blocks(text):
    """(first line number, code, skipped) for each python block."""
    for match in BLOCK.finditer(text):
        line = text.count("\n", 0, match.start(2)) + 1
        yield line, match.group(2), bool(match.group(1))


@pytest.mark.parametrize("doc", DOCS)
def test_every_python_block_runs(doc, monkeypatch):
    path = ROOT / doc
    if not path.exists():  # the sdist ships the tests but not docs/
        pytest.skip(f"{doc} is not in this checkout")
    module = types.ModuleType(f"docs_{path.stem}")
    monkeypatch.setitem(sys.modules, module.__name__, module)  # dataclasses look it up

    ran = 0
    for line, code, skipped in blocks(path.read_text()):
        if skipped:
            continue
        # Padding keeps line numbers, so a traceback points into the Markdown file.
        exec(compile("\n" * (line - 1) + code, str(path), "exec"), module.__dict__)  # noqa: S102
        ran += 1
    assert ran, f"no python blocks found in {doc}"


def test_blocks_finds_fences_and_skip_markers():
    text = "x\n```python\na = 1\n```\n<!-- skip-doctest -->\n```python\nb\n```\n"
    assert list(blocks(text)) == [(3, "a = 1\n", False), (7, "b\n", True)]
