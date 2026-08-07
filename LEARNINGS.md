# Learnings

Running notes on non-obvious design decisions and Python/tooling concepts encountered while building this project.

## Money as integer cents, never float

Floats use IEEE 754 binary floating point, which can't exactly represent most base-10 decimal fractions (`0.1 + 0.2 != 0.3`). Errors are tiny individually but compound across many summed transactions, and can break exact-equality checks (e.g. reconciling parsed transactions against a statement's running balance).

Fix: never let an amount touch `float` at any point in the pipeline. Convert straight from the raw string to `decimal.Decimal` (constructed from the string, not from a float — `Decimal("19.99")`, not `Decimal(19.99)`), multiply by 100, then `int()`. This is why APIs like Stripe's represent money as plain integers.

## `ABC` / `abstractmethod`

`ABC` (from the `abc` module) enforces an interface contract at runtime, not just by convention. `StatementParser` has no real parsing logic of its own — there's no generic algorithm that reads every bank's PDF layout — so it's deliberately incomplete. Without `ABC`, that incompleteness would only surface later: someone could instantiate `StatementParser` directly, or write a subclass that forgets to implement `parse`, and the bug wouldn't show up until something actually called `.parse()`. With `ABC` + `@abstractmethod`, Python raises `TypeError` at the moment you try to instantiate an incomplete subclass, catching the mistake immediately instead of downstream.

## `__init__.py`

Makes a directory a proper Python package so dotted imports (`expense_analyser.parsers.base`) resolve reliably. Python does support "implicit namespace packages" (folders without `__init__.py` sometimes still import), but they're inconsistent across tooling. We hit exactly this class of bug once already: pytest couldn't resolve `expense_analyser` until the project root was explicitly added via `pyproject.toml`'s `pythonpath` setting. Keeping every package explicit avoids repeating that.

## The parser registry pattern

`PARSER_REGISTRY` (in `parsers/registry.py`) maps an `account_id` string to the `StatementParser` subclass that knows how to read that account's PDF layout. Without it, the ingestion pipeline would need a growing `if/elif` chain — one branch per bank — meaning every new account requires editing shared ingestion code. With the registry, adding a new bank means: write one new `StatementParser` subclass, add one line to the dict. The ingestion pipeline itself never changes.

## Idempotent inserts via `INSERT OR IGNORE` + `UNIQUE`

Re-running ingestion on overlapping statements is expected (new PDFs added to an already-ingested folder, etc.). Rather than querying "does this transaction already exist" before every insert (racy, extra round-trip), a `UNIQUE` constraint on a `dedup_hash` column lets `INSERT OR IGNORE` handle it in one statement — SQLite silently skips rows that would violate the constraint.

## Generators, `yield`, and FastAPI's `lifespan`

A normal function runs top to bottom and returns once. A function containing `yield` is a **generator** instead: calling it doesn't run the body — it runs *up to* the next `yield`, hands a value back, and then pauses in place. Resuming it later picks up execution right after that `yield`, with all local state intact:

```python
def demo():
    print("before")
    yield "some value"
    print("after")
```

Driving `demo()` to completion prints `before`, yields `"some value"`, then (on resume) prints `after`. Nothing after `yield` runs until something explicitly resumes it.

Wrapping a generator with `@contextmanager` (or `@asynccontextmanager` for `async def`) turns "code before `yield`" into a `with` block's setup, and "code after `yield`" into its guaranteed teardown — the same idea as `open()`, just written by hand.

FastAPI's `lifespan` uses exactly this pattern, but scoped to the whole app's runtime instead of one `with` block:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.repo = TransactionRepository(DB_PATH)   # setup: runs once, at boot
    yield                                               # server serves requests while paused here
    app.state.repo.connection.close()                  # teardown: runs once, at shutdown
```

It's called **once**, not once-per-phase: uvicorn invokes it at startup, execution runs until `yield` and pauses there for the app's entire lifetime, then resumes and finishes on shutdown. This replaced a version of `get_repo` that opened a brand-new, never-closed SQLite connection on every single request — a real connection leak, since nothing called `.close()` on the old per-request repo.

Gotcha hit while building this: `@asynccontextmanager` requires the wrapped function to actually contain `yield` — a typo'd keyword (`yeild` instead of `yield`) means Python parses the function as an ordinary one-shot coroutine, not a generator. Calling `lifespan(app)` then returns a plain coroutine object instead of something pausable, and Starlette's `anext(self.gen)` fails with `TypeError: 'coroutine' object is not an async iterator` — a confusing error whose real cause is a misspelled keyword, not an async/await mistake.

## CI via GitHub Actions

Before this, `pytest` only ran when someone remembered to type it locally — nothing re-checked a change on push. `.github/workflows/tests.yml` fixes that: a YAML file GitHub itself watches for and runs automatically.

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest
```

The vocabulary: `on` is the trigger (which events cause a run); a **job** (`test`) is a unit of work that gets its own fresh VM (`runs-on`); `strategy.matrix` reruns the same job once per listed value — here, once per Python version, to catch version-specific breakage instead of only testing whatever's installed locally; a **step** is either `uses:` (run a prebuilt, shareable action — `actions/checkout` clones the repo onto the VM, since it starts empty) or `run:` (execute a raw shell command, same as typing it into a terminal on that VM).

Three ways to check a workflow is actually correct, in increasing order of confidence:
1. Read it against the schema above — `on`/`jobs.<id>.runs-on`/`jobs.<id>.steps` present and sensible. Catches obvious structural mistakes; YAML is indentation-sensitive, so this pass is worth doing carefully.
2. Simulate the `run:` steps locally (exactly what CI will do: `pip install -r requirements.txt`, then `pytest`) — catches "do the tests actually pass" and "are dependencies listed correctly," which is most of what breaks. Doesn't catch YAML syntax errors or typos in action names/versions.
3. Push it and watch the Actions tab. The only real ground truth — GitHub validates the YAML itself (a malformed file shows "Invalid workflow file" instead of running), and a valid one gives a genuine pass/fail from an actual run, not a simulation.