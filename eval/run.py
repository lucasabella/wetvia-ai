"""Command-line entry point for retrieval, A/B and dataset validation."""

import sys

from wetvia_eval.ab_eval import main as ab_main
from wetvia_eval.retrieval_eval import main as retrieval_main
from wetvia_eval.validate import main as validate_main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ab":
        raise SystemExit(ab_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        raise SystemExit(validate_main(sys.argv[2:]))
    retrieval_main()
