"""Command-line entry point for retrieval and A/B evaluation."""

import sys

from wetvia_eval.ab_eval import main as ab_main
from wetvia_eval.retrieval_eval import main as retrieval_main

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ab":
        raise SystemExit(ab_main(sys.argv[2:]))
    retrieval_main()
