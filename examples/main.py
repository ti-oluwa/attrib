import sys
import attrib_example
import attrs_example
import pydantic_example
import utils


DEFAULT_ITERATIONS = 10000


def main(n: int) -> None:
    """Main function to run the benchmarks."""
    attrs_example.test(n)
    pydantic_example.test(n)
    attrib_example.test(n)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
        except ValueError:
            utils.log(f"Invalid argument. Using default value of {DEFAULT_ITERATIONS}.")
            n = DEFAULT_ITERATIONS
    else:
        n = DEFAULT_ITERATIONS

    utils.log(f"Running benchmarks with {n} iterations...")
    main(n)
