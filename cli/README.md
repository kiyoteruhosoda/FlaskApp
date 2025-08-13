# PhotoNest CLI (`fpv`)

Minimal CLI skeleton. `fpv --help` shows the help screen and subcommand usage.

## Install (editable)

```bash
cd cli
python -m pip install -e .
```

## Sync (dry-run outline)

First apply the DDL and check configuration:

```bash
fpv config check
```

Run dry-run (records job history and outputs structured logs):

```bash
fpv sync --dry-run
# Single account only:
# fpv sync --single-account --account-id 1 --dry-run
```

`--no-dry-run` will be effective in later steps when the actual API implementation is added.
