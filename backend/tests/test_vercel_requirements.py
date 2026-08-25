"""Guards the Vercel function's dependency list against what it actually imports.

The serverless deployment installs from the root `requirements.txt`, a
deliberately trimmed list -- no numpy, no massive, no litellm -- while the
container installs `backend/pyproject.toml` in full. Nothing held the two in
step, so a dependency added for the container and imported at module scope took
the whole function down: `app.main` failed to import and every `/api/*` route
returned 500, `/api/health` included.

The walk starts at `app.main` (what `api/index.py` imports) and follows only
imports that run at import time, so a package reached solely from inside a
function stays off the list -- which is exactly how the trimmed set survives.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements.txt"
ENTRYPOINT = "app.main"


def _canonical(name: str) -> str:
    """PEP 503 normalisation, so `python_dotenv` and `python-dotenv` match."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _module_path(dotted: str) -> Path | None:
    """Locate an internal module on disk, or None if it is not one."""
    parts = dotted.split(".")
    if parts[0] != "app":
        return None
    base = ROOT / "backend" / Path(*parts)
    for candidate in (base / "__init__.py", base.with_suffix(".py")):
        if candidate.is_file():
            return candidate
    return None


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _import_time_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Yield the nodes that execute when the module is imported.

    Function bodies are skipped because they run on call, not on import -- the
    distinction the trimmed requirements list depends on. `if TYPE_CHECKING:`
    blocks are skipped for the same reason: they never run at all.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(child, ast.If) and _is_type_checking(child.test):
            continue
        yield child
        yield from _import_time_nodes(child)


def _enqueue(queue: list[str], dotted: str) -> None:
    """Queue an internal module and every package above it.

    `from .db.postgres import normalize_dsn` names one module, but importing it
    executes `app/__init__.py` and `app/db/__init__.py` first. Queueing only
    what the import statement spells would leave those unparsed.
    """
    parts = dotted.split(".")
    queue.extend(".".join(parts[: i + 1]) for i in range(len(parts)))


def _walk() -> tuple[set[str], set[str]]:
    """Follow import-time imports from the entrypoint.

    Returns the third-party top-level module names reached, and the internal
    modules visited getting there.
    """
    third_party: set[str] = set()
    visited: set[str] = set()
    queue: list[str] = []
    _enqueue(queue, ENTRYPOINT)

    while queue:
        dotted = queue.pop()
        if dotted in visited:
            continue
        path = _module_path(dotted)
        if path is None:
            continue
        visited.add(dotted)
        package = dotted if path.name == "__init__.py" else dotted.rpartition(".")[0]

        for node in _import_time_nodes(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == "app":
                        _enqueue(queue, alias.name)
                    elif top not in sys.stdlib_module_names:
                        third_party.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package
                    for _ in range(node.level - 1):
                        base = base.rpartition(".")[0]
                    target = f"{base}.{node.module}" if node.module else base
                else:
                    target = node.module or ""
                    top = target.split(".")[0]
                    if top != "app":
                        if top and top not in sys.stdlib_module_names:
                            third_party.add(top)
                        continue
                # A name imported from a package may be a submodule rather than
                # an attribute -- `from .history import router` is how main.py
                # reaches history/router.py -- so both are followed.
                _enqueue(queue, target)
                for alias in node.names:
                    queue.append(f"{target}.{alias.name}")

    return third_party, visited


def _declared() -> set[str]:
    names = set()
    for line in REQUIREMENTS.read_text().splitlines():
        requirement = line.split("#")[0].strip()
        if not requirement:
            continue
        names.add(_canonical(re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0]))
    return names


def _distributions(module: str) -> set[str]:
    """The distributions that provide an importable module.

    Read from the installed metadata rather than a hand-kept table, so
    `dotenv` resolves to `python-dotenv` without this file having to know it.
    """
    provided = packages_distributions().get(module, [])
    return {_canonical(name) for name in provided} or {_canonical(module)}


@pytest.fixture(scope="module")
def walked() -> tuple[set[str], set[str]]:
    return _walk()


def test_every_import_time_dependency_is_declared(walked):
    third_party, _ = walked
    declared = _declared()
    missing = sorted(m for m in third_party if not _distributions(m) & declared)
    assert not missing, (
        f"{missing} are imported at import time from {ENTRYPOINT} but absent "
        f"from {REQUIREMENTS.name}; the Vercel function will fail to import"
    )


def test_the_walk_reaches_the_cookie_signer(walked):
    """Without this the guard above passes vacuously: a walk that resolved
    nothing would report no missing dependencies at all."""
    third_party, visited = walked
    assert "app.identity.cookie" in visited
    assert "itsdangerous" in third_party


def test_the_walk_parses_every_package_along_the_way(walked):
    """Importing `app.main` executes `app/__init__.py` first, and every
    intermediate `__init__.py` after it. A module-scope third-party import in
    one of those takes the function down exactly as cookie.py did, so a walk
    that reaches a module without reaching its package has a blind spot."""
    _, visited = walked
    ancestors = {module.rpartition(".")[0] for module in visited if "." in module}
    assert ancestors <= visited, f"packages reached but never parsed: {sorted(ancestors - visited)}"


@pytest.mark.parametrize("module", ["numpy", "massive", "litellm"])
def test_packages_imported_lazily_stay_out_of_the_walk(walked, module):
    """The three the trimmed list exists to exclude. Each is imported inside a
    function, so the function never pays for them -- and if one migrates to
    module scope, the guard above starts demanding it be declared."""
    third_party, _ = walked
    assert module not in third_party
