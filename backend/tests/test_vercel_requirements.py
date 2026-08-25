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

## What this does NOT cover on its own

The walk above only parses first-party `app.*` source, so it records that
`app.auth.providers` imports `authlib` and stops there -- it never looks at
what authlib itself imports. That blind spot shipped a real outage: authlib's
`integrations.starlette_client` reaches `integrations.httpx_client`, which
imports `httpx` at module scope, and authlib's own package metadata does not
declare `httpx` as a dependency (only `cryptography` and `joserfc>=1.6.0` --
confirmed via `importlib.metadata.requires("authlib")`). A metadata-only check
-- reading `Requires-Dist` on the packages `app.*` imports directly -- cannot
catch this: the whole failure mode IS a package that fails to declare what it
imports. The second half of this file (`_walk_package_internals`) instead
parses the *source* of every third-party package `app.*` imports directly,
one hop into each, and follows its own module-scope imports for as long as
they stay inside that same top-level package. What it finds there and does
NOT already declare is checked against `requirements.txt` -- allowing
anything transitively guaranteed by a *declared* package's own `Requires-Dist`
(e.g. `anyio`, pulled in unconditionally once `httpx` is declared), since that
much pip/uv already enforces for us.

This is deliberately bounded to one hop per directly-imported package: it does
not chase the further dependencies of packages reached *outside* that hop
(e.g. once the walk reaches `httpx` from inside `authlib`, it does not also
parse httpx's own source for a third hop). A full transitive resolver would
mean reimplementing pip's dependency graph; what actually failed here was one
specific, checkable thing -- a package imported directly by this app, itself
importing something at load time that it does not declare and that
`requirements.txt` does not carry either. That is what is covered. A second-
or third-order version of the same bug (an undeclared import inside a package
that authlib's own internals reach, rather than inside authlib itself) is
NOT covered by this guard.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, packages_distributions, requires
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


def _resolve_branch(test: ast.expr) -> bool | None:
    """Evaluate a side-effect-free `if` condition the way Python itself would
    when actually importing the file -- e.g. `if sys.version_info < (3, 11):`,
    the standard shape for a version-conditional import (asyncpg's own
    `async_timeout` backport, used only before 3.11, is exactly this; without
    resolving it the walk below would demand `async_timeout` be declared on
    an interpreter where that branch never runs). Returns None when the
    condition can't be evaluated in this restricted namespace, so an
    unfamiliar condition walks both branches rather than silently picking one
    -- that can only make the guard ask for an extra package, never miss a
    real one.
    """
    try:
        code = compile(ast.Expression(body=test), "<branch>", "eval")
        return bool(eval(code, {"__builtins__": {}}, {"sys": sys}))  # noqa: S307
    except Exception:
        return None


def _import_time_nodes(node: ast.AST) -> Iterator[ast.AST]:
    """Yield the nodes that execute when the module is imported.

    Function bodies are skipped because they run on call, not on import -- the
    distinction the trimmed requirements list depends on. `if TYPE_CHECKING:`
    blocks are skipped for the same reason: they never run at all. A
    resolvable `if` (see `_resolve_branch`) only yields the branch that
    actually runs on this interpreter. `try:` bodies are skipped too --
    app/*.py has none of these today, but the package-internals walk below
    runs this same function over third-party source, where
    `try: import x except ImportError: ...` is the standard shape for an
    optional dependency. Treating that as a hard requirement would make the
    guard demand packages that were never actually needed; skipping it means
    the guard can under-report a genuinely-required import hidden inside an
    unrelated `try`, which is the safer direction to be wrong in.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.Try):
            continue
        if isinstance(child, ast.If):
            if _is_type_checking(child.test):
                continue
            resolved = _resolve_branch(child.test)
            if resolved is not None:
                for stmt in child.body if resolved else child.orelse:
                    yield stmt
                    yield from _import_time_nodes(stmt)
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


def _walk() -> tuple[set[str], set[str], set[str]]:
    """Follow import-time imports from the entrypoint.

    Returns the third-party top-level module names reached, the internal
    modules visited getting there, and the exact dotted names third-party
    modules were imported as (e.g. `authlib.integrations.starlette_client`,
    not just `authlib`) -- the entrypoints `_walk_package_internals` starts
    from, since which submodule of a package app.* actually reached is what
    determines which of that package's own imports run.
    """
    third_party: set[str] = set()
    visited: set[str] = set()
    entrypoints: set[str] = set()
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
                        entrypoints.add(alias.name)
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
                            entrypoints.add(target)
                        continue
                # A name imported from a package may be a submodule rather than
                # an attribute -- `from .history import router` is how main.py
                # reaches history/router.py -- so both are followed.
                _enqueue(queue, target)
                for alias in node.names:
                    queue.append(f"{target}.{alias.name}")

    return third_party, visited, entrypoints


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


def _requires_closure(dist_name: str, seen: set[str] | None = None) -> set[str]:
    """Every distribution `dist_name` unconditionally pulls in, transitively.

    `pip`/`uv` installs these automatically once `dist_name` itself is
    declared, so a package found only here does not need its own line in
    `requirements.txt` -- unlike a package that is imported but never
    declared anywhere in this closure, which is exactly the bug class this
    file exists to catch. Requirements gated by an environment marker
    (`extra == "..."`, `python_version < "..."`, etc.) are skipped rather
    than assumed present -- an optional extra is not installed unless
    something asks for the extra, so counting it as satisfied could hide a
    real gap. That means this closure can under-count (treat a
    marker-gated-but-actually-applicable dependency as unsatisfied), which
    only makes the guard stricter, never blinder.
    """
    seen = set() if seen is None else seen
    canonical = _canonical(dist_name)
    if canonical in seen:
        return seen
    seen.add(canonical)
    try:
        declared_requires = requires(dist_name) or []
    except PackageNotFoundError:
        return seen
    for requirement in declared_requires:
        if ";" in requirement:  # marker-gated (extras, python_version, ...) -- not guaranteed
            continue
        name = re.split(r"[<>=!~\[ ]", requirement, maxsplit=1)[0].strip()
        if name:
            _requires_closure(name, seen)
    return seen


def _site_package_source(dotted: str) -> Path | None:
    """The `.py` file backing an installed third-party module, or None for a
    namespace package, a compiled extension, or a name that isn't importable
    at all -- any of which just ends that branch of the walk."""
    try:
        spec = importlib.util.find_spec(dotted)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
        return None
    return Path(spec.origin)


def _walk_package_internals(entrypoints: set[str]) -> tuple[set[str], set[str]]:
    """From each third-party module app.* imports directly, follow its own
    module-scope imports for as long as they stay inside that same top-level
    package -- the hop that catches authlib importing httpx without
    declaring it. See the module docstring for what this deliberately does
    not chase.

    Returns the third-party module names reached this way (the "leaves" --
    imports that left the home package, so they were not walked further) and
    the internal (within-package) dotted names visited getting there.
    """
    leaves: set[str] = set()
    visited: set[str] = set()
    queue: list[str] = list(entrypoints)

    while queue:
        dotted = queue.pop()
        if dotted in visited:
            continue
        visited.add(dotted)
        home = dotted.split(".")[0]
        path = _site_package_source(dotted)
        if path is None:
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover -- no such package today
            continue
        package = dotted if path.name == "__init__.py" else dotted.rpartition(".")[0]

        for node in _import_time_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == home:
                        queue.append(alias.name)
                    elif top not in sys.stdlib_module_names:
                        leaves.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = package
                    for _ in range(node.level - 1):
                        base = base.rpartition(".")[0]
                    target = f"{base}.{node.module}" if node.module else base
                    queue.append(target)
                    for alias in node.names:
                        queue.append(f"{target}.{alias.name}")
                else:
                    target = node.module or ""
                    top = target.split(".")[0]
                    if top == home:
                        queue.append(target)
                        for alias in node.names:
                            queue.append(f"{target}.{alias.name}")
                    elif top and top not in sys.stdlib_module_names:
                        leaves.add(top)

    return leaves, visited


@pytest.fixture(scope="module")
def walked() -> tuple[set[str], set[str], set[str]]:
    return _walk()


@pytest.fixture(scope="module")
def package_internals(walked) -> tuple[set[str], set[str]]:
    _, _, entrypoints = walked
    return _walk_package_internals(entrypoints)


def test_every_import_time_dependency_is_declared(walked):
    third_party, _, _ = walked
    declared = _declared()
    missing = sorted(m for m in third_party if not _distributions(m) & declared)
    assert not missing, (
        f"{missing} are imported at import time from {ENTRYPOINT} but absent "
        f"from {REQUIREMENTS.name}; the Vercel function will fail to import"
    )


def test_the_walk_reaches_the_cookie_signer(walked):
    """Without this the guard above passes vacuously: a walk that resolved
    nothing would report no missing dependencies at all."""
    third_party, visited, _ = walked
    assert "app.identity.cookie" in visited
    assert "itsdangerous" in third_party


def test_the_walk_parses_every_package_along_the_way(walked):
    """Importing `app.main` executes `app/__init__.py` first, and every
    intermediate `__init__.py` after it. A module-scope third-party import in
    one of those takes the function down exactly as cookie.py did, so a walk
    that reaches a module without reaching its package has a blind spot."""
    _, visited, _ = walked
    ancestors = {module.rpartition(".")[0] for module in visited if "." in module}
    assert ancestors <= visited, f"packages reached but never parsed: {sorted(ancestors - visited)}"


@pytest.mark.parametrize("module", ["numpy", "massive", "litellm"])
def test_packages_imported_lazily_stay_out_of_the_walk(walked, module):
    """The three the trimmed list exists to exclude. Each is imported inside a
    function, so the function never pays for them -- and if one migrates to
    module scope, the guard above starts demanding it be declared."""
    third_party, _, _ = walked
    assert module not in third_party


def test_import_time_deps_of_directly_imported_packages_are_declared(package_internals):
    """The guard `test_every_import_time_dependency_is_declared` could not
    have caught: a package `app.*` imports directly (authlib) itself imports
    a third-party module at load time (httpx) that neither authlib's own
    metadata nor requirements.txt declares. A leaf is allowed to be missing
    from requirements.txt only if it is guaranteed to arrive anyway, as a
    transitive, unconditional dependency of something that IS declared."""
    leaves, _ = package_internals
    declared = _declared()
    satisfied = set(declared)
    for name in declared:
        satisfied |= _requires_closure(name)
    missing = sorted(leaf for leaf in leaves if not _distributions(leaf) & satisfied)
    assert not missing, (
        f"{missing} are imported at import time by a package {ENTRYPOINT} imports directly, "
        f"but are declared neither in {REQUIREMENTS.name} nor as an unconditional dependency of "
        "anything that is; the Vercel function will fail to import"
    )


def test_the_package_internals_walk_reaches_httpx_through_authlib(package_internals):
    """Without this the guard above passes vacuously. This is the walk that
    the C1 outage needed and the original guard didn't have: parsing
    authlib's own source (not just its declared metadata, which does not
    mention httpx at all) to see that `integrations.starlette_client` reaches
    `integrations.httpx_client`, which does `import httpx` at module scope."""
    leaves, visited = package_internals
    assert "httpx" in leaves
    assert any(module.startswith("authlib.integrations.httpx_client") for module in visited)


def test_an_undeclared_leaf_would_be_reported_missing(package_internals):
    """Proves the new check actually fails shut, by reproducing exactly the
    C1 bug's shape without touching requirements.txt: simulate httpx being
    absent from the declared set (as it was before that fix) and confirm the
    satisfied-by-closure logic still flags it, rather than silently treating
    it as covered by something else."""
    leaves, _ = package_internals
    declared_without_httpx = _declared() - {"httpx"}
    satisfied = set(declared_without_httpx)
    for name in declared_without_httpx:
        satisfied |= _requires_closure(name)
    missing = {leaf for leaf in leaves if not _distributions(leaf) & satisfied}
    assert "httpx" in missing


def test_a_transitively_guaranteed_leaf_is_not_reported_missing(package_internals):
    """The other side of the same logic: `anyio` is imported at module scope
    from inside authlib's httpx_client integration too, but it is never
    declared anywhere in this repo. It should NOT be reported missing,
    because it is an unconditional dependency of `httpx`, which IS declared
    -- pip/uv installs it automatically, so demanding a redundant line in
    requirements.txt for it would just be noise."""
    leaves, _ = package_internals
    assert "anyio" in leaves  # otherwise this test is checking nothing
    declared = _declared()
    satisfied = set(declared)
    for name in declared:
        satisfied |= _requires_closure(name)
    assert _distributions("anyio") & satisfied
