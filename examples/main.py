import typing

import click

import attrib_
import attrs_
import utils

DEFAULT_ITERATIONS = 10000


@click.command()
@click.option(
    "-n",
    "--iterations",
    default=DEFAULT_ITERATIONS,
    type=int,
    help=f"Number of iterations to run (default: {DEFAULT_ITERATIONS})",
    show_default=True,
)
@click.option(
    "-o",
    "--operation",
    type=click.Choice(
        ["serialization", "deserialization", "both"], case_sensitive=False
    ),
    default="serialization",
    help="Operation to benchmark: serialization, deserialization, or both",
    show_default=True,
)
@click.option(
    "-m",
    "--mode",
    type=click.Choice(["python", "json"], case_sensitive=False),
    default="python",
    help="Serialization mode: python (dict) or json (string)",
    show_default=True,
)
@click.option(
    "-l",
    "--library",
    type=click.Choice(["attrib", "attrs", "both"], case_sensitive=False),
    default="both",
    help="Library to benchmark: attrib, attrs, or both",
    show_default=True,
)
def main(iterations: int, operation: str, mode: str, library: str) -> None:
    """Run benchmarks for attrib and attrs libraries.

    This CLI tool allows you to compare the performance of attrib and attrs
    for serialization and deserialization operations.

    Examples:

        # Run both libraries with default settings
        python main.py

        # Run 50000 iterations of serialization only
        python main.py -n 50000 -o serialization

        # Run deserialization with JSON mode
        python main.py -o deserialization -m json

        # Benchmark only attrib library
        python main.py -l attrib -n 20000
    """
    operation = operation.lower()
    mode_literal: typing.Literal["python", "json"] = typing.cast(
        typing.Literal["python", "json"], mode.lower()
    )
    library = library.lower()

    utils.log(f"Running benchmarks with {iterations} iterations...")
    utils.log(f"Operation: {operation}")
    utils.log(f"Mode: {mode_literal}")
    utils.log(f"Library: {library}")
    utils.log("-" * 60)

    # Run attrib benchmarks
    if library in ["attrib", "both"]:
        if operation in ["serialization", "both"]:
            attrib_.test_serialization(iterations, mode=mode_literal)

        if operation in ["deserialization", "both"]:
            attrib_.test_deserialization(iterations)

    # Run attrs benchmarks
    if library in ["attrs", "both"]:
        if operation in ["serialization", "both"]:
            attrs_.test_serialization(iterations, mode=mode_literal)

        if operation in ["deserialization", "both"]:
            attrs_.test_deserialization(iterations)


if __name__ == "__main__":
    main()
