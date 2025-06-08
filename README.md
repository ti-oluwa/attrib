# attrib

`attrib` is a performant data description and validation system for Python. It provides an intuitive API for describing and validating data structures using Python's descriptor protocol. `attrib` is designed to be deterministic, familiar, and flexible, allowing you to create complex data structures with no hidden runtime magic.

In most cases, especially heavy workflows, `attrib` can be 5 - 30% faster than `attrs` + `cattrs`, `dataclasses` + `cattrs`, or `pydantic` when serializing and deserializing data.

`attrib` dataclasses can be used in latency sensitive APIs, configuration definitions, and data pipelines.

## What does `attrib` offer?

- Declarative, intuitive and easily extensible API
- Fast and lightweight. Low OOP overhead and no hidden runtime magic.
- Recursive deserialization of complex or nested data structures.
- Composable, functional, and flexible validation.
- Enforces validation of field values on set.
- Context-aware deserialization and validation.
- Declarative serialization control with the `Options` API
- Growing set of custom fields, validators, and utilities.
- Adequately typed APIs for better IDE support.
- Detailed error handling with error history and context preservation.
- Type adapter API for adapted types (WIP)
- Supports Python 3.8+

> This library is still in early development and may only be used for testing and experimentation.

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

Proper documentation and tests will be included soon, but you can check the [examples](/attrib/examples/) directory for usage patterns, or run:

```bash

uv run --python 3.10 --with-requirements 'dev-requirements.txt' examples/main.py 1000 -OO -B
```

to run benchmarks of `attrib` against `attrs + cattrs` and `pydantic`.

I would love to hear your feedback, suggestions, or contributions. Feel free to open an issue or a pull request.
