# 0004. Contract tests run real Hermes releases

Status: Accepted

## Context

The unit tests replace `hermes_cli.web_server` with a stub. A Hermes release that renames the public-path set or the
session token, or changes how dashboard plugins are discovered, would pass them and still break the plugin.

`pip install` from a Hermes release tag does not resolve: its exact pins conflict, and only the `[tool.uv]` overrides
in Hermes's `pyproject.toml` with its `uv.lock` make the set installable. Hermes also declares its dependencies for
Python 3.14 only.

## Decision

`tests/contract/` copies the plugin into a temporary Hermes home, enables it in `config.yaml`, imports the real
`hermes_cli.web_server.app` and calls the plugin routes with FastAPI's `TestClient`, using synthetic credentials and
signed `initData`.

CI installs each release listed in `compat/hermes-versions.json` the way Hermes does: a shallow clone of the tag and
`uv sync --frozen --no-dev` on the Python version named in that file. One `hermes-contract` job runs per release.
`HERMES_CONTRACT_REQUIRED=1` turns a missing Hermes into a failure instead of a skip, and `HERMES_EXPECT_VERSION`
checks that the installed release is the one the job claims to test.

## Consequences

Supporting a new Hermes release is one line in `compat/hermes-versions.json`. Without Hermes installed the contract tests
are skipped, so the unit run needs nothing new. If installing Hermes in CI stops working, the fallback is to put the
cloned source on `PYTHONPATH` with only the dashboard's own dependencies installed; record that as a new decision.
