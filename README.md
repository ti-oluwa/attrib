# attrib

`attrib` is a performant and lightweight data description library for Python. It provides an intuitive API for describing and validating data structures using Python's descriptor protocol. `attrib` is designed to be familiar and flexible, allowing you to create complex data structures with minimal boilerplate code.

It provides an API similar to `attrs`, but with a focus on performance and simplicity. In most cases, `attrib` can be 5 - 30% faster than `attrs` + `cattrs` or even `pydantic`.

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
