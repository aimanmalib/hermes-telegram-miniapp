# Hermes versions under test

`hermes-versions.json` is the single list of Hermes Agent releases the contract tests run against.

- `minimum`: the oldest release the plugin supports. It must also appear in `uji` and match `requires_hermes` in
  `plugin/plugin.yaml`.
- `uji`: every release tag the `hermes-contract` CI job installs and tests (one matrix entry per tag).
- `python`: the interpreter the job uses. Hermes installs its dependencies only on Python 3.14.

To test a new Hermes release, add its tag to `uji`. No code change is needed.

## Running the contract tests locally

```sh
git clone --depth 1 --branch v0.23.0 https://github.com/NousResearch/hermes-agent /tmp/hermes
(cd /tmp/hermes && uv sync --frozen --no-dev --python 3.14)
uv pip install --python /tmp/hermes/.venv/bin/python -r tests/contract/requirements.txt
HERMES_CONTRACT_REQUIRED=1 /tmp/hermes/.venv/bin/python -m pytest tests/contract
```

Without Hermes installed, `python -m pytest` skips these tests.
