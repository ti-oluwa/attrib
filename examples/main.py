import sys
import attrib_
import dataclass_
import attrs_
import utils


DEFAULT_ITERATIONS = 10000


def main(n: int) -> None:
    """Main function to run the benchmarks."""
    attrib_.test(n)
    dataclass_.test(n)
    attrs_.test(n)


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
