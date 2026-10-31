"""Pure formatting helpers for multilingual-e5-large-instruct inputs."""


def format_document_input(
    regeling_titel: str,
    kop_pad: str,
    artikel: str,
    opschrift: str | None,
    tekst: str,
) -> str:
    """Format a legal chunk as a passage, without a ``passage:`` prefix."""
    return f"{regeling_titel} | {kop_pad} | Artikel {artikel} ({opschrift or ''})\n{tekst}"


def format_query_input(task: str, query: str) -> str:
    """Format a query using the instruction form documented by the model card."""
    return f"Instruct: {task}\nQuery: {query}"
