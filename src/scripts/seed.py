"""Load src/fixtures/*.json into Postgres. `--reset` truncates first."""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.parse_args()
    raise NotImplementedError("Phase 0 Day 3")


if __name__ == "__main__":
    main()
