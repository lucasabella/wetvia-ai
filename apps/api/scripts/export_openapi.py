"""Write the checked-in OpenAPI artifact using the app factory only."""

import argparse
from pathlib import Path

from wetvia.api.openapi_export import export_openapi

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT = _REPOSITORY_ROOT / "packages" / "api-client" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="output path (default: packages/api-client/openapi.json)",
    )
    arguments = parser.parse_args()
    export_openapi(arguments.output)


if __name__ == "__main__":
    main()
