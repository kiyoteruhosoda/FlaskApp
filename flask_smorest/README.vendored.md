# Vendored `flask_smorest`

This directory contains a vendored copy of [`flask-smorest`](https://github.com/marshmallow-code/flask-smorest) version 0.46.2.

We vendor the package so that the test suite can run in minimal environments that do not pre-install optional dependencies. When running in production, the real package should still be installed via `requirements.txt` or `pyproject.toml`; Python will prefer the site-packages installation when present.

The upstream project is distributed under the terms of the MIT License, which is reproduced in `LICENSE`.
