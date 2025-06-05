# attrib

`attrib` is a performant and lightweight data description library for Python. It provides an intuitive API for describing and validating data structures using Python's descriptor protocol. `attrib` is designed to be familiar and flexible, allowing you to create complex data structures with minimal boilerplate code.

It provides an API similar to `attrs`, but with a focus on performance and simplicity. In most cases, `attrib` can be 7 - 50% faster than `attrs` + `cattrs` or even `pydantic`.

`attrib` dataclasses can be used for describing, validating, and serializing data in APIs, configuration definitions, and data processing pipelines.

## Features

- Simple, intuitive and extensible API
- Supports complex data structures
- Fast and lightweight
- Built-in validation and serialization
- Selective serialization - specify which fields to include or exclude, depth, etc.
- Growing set of custom types, fields and validators
- Fully typed APIs for better IDE support
- Type adapter API for adapted types

> **Note**: This library is still in early development and may only be used for testing and experimentation.

## Quick Setup with `uv`

To get started with `attrib`, clone the repository.

Please ensure you have `uv` installed. If not, visit [uv's documentation](https://docs.astral.sh/uv/getting-started/installation/) for installation instructions.

Next, ensure you have python installed. If you do not, run these commands.

Check available python versions:

```bash
uv install python --list
```

Install version of choice:

```bash
uv install python <version>
```

> Ensure the version installed is compatible with the version specified in `.python-version` (3.10.*), or delete `.python-version` and install a version >=3.10. Although, there is potential support for Python 3.8+.

For the purpose of testing, install the dev requirements:

```bash
uv install --requirements dev-requirements.txt
```

Proper documentation and tests will be included soon, but you can check the [examples](/attrib/examples/) directory for usage patterns, or run:

```bash

uv run examples/main.py 1000 -OO -B
```

to run benchmarks of `attrib` against `attrs + cattrs` and `pydantic`.

I would love to hear your feedback, suggestions, or contributions. Feel free to open an issue or a pull request.
