"""Pure input formatting and stubbed local-adapter coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import wetvia.embeddings.adapters.sentence_transformers as sentence_transformers_adapter
from wetvia.embeddings import format_document_input, format_query_input
from wetvia.embeddings.adapters.sentence_transformers import SentenceTransformersEmbedder


class _ModelStub:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.encode_calls: list[tuple[list[str], dict[str, object]]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return len(self.vectors[0]) if self.vectors else 2

    def encode(self, texts: list[str], **kwargs: object) -> list[list[float]]:
        self.encode_calls.append((texts, kwargs))
        return self.vectors


def _torch_stub(*, cuda: bool, mps: bool) -> SimpleNamespace:
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
        float16=object(),
        float32=object(),
    )


def test_document_format_follows_verified_model_card_without_passage_prefix() -> None:
    formatted = format_document_input(
        "Besluit bouwwerken leefomgeving",
        "Hoofdstuk 2 | Afdeling 2.3",
        "2.29",
        "Dakkapellen",
        "De tekst van het artikel.",
    )

    assert formatted == (
        "Besluit bouwwerken leefomgeving | Hoofdstuk 2 | Afdeling 2.3 | "
        "Artikel 2.29 (Dakkapellen)\nDe tekst van het artikel."
    )
    assert not formatted.startswith("passage:")


def test_document_format_handles_missing_optional_heading() -> None:
    assert format_document_input("Wet", "Hoofdstuk 1", "1", None, "Tekst") == (
        "Wet | Hoofdstuk 1 | Artikel 1 ()\nTekst"
    )


def test_query_format_uses_instruction_and_query_lines() -> None:
    assert format_query_input("Find relevant law", "Hoe hoog mag een dakkapel zijn?") == (
        "Instruct: Find relevant law\nQuery: Hoe hoog mag een dakkapel zijn?"
    )


@pytest.mark.parametrize(
    ("cuda", "mps", "expected_device", "expected_dtype"),
    [
        (True, True, "cuda", "float16"),
        (False, True, "mps", "float16"),
        (False, False, "cpu", "float32"),
    ],
)
def test_adapter_selects_device_and_dtype_and_normalizes(
    cuda: bool,
    mps: bool,
    expected_device: str,
    expected_dtype: str,
) -> None:
    model = _ModelStub([[3.0, 4.0]])
    torch = _torch_stub(cuda=cuda, mps=mps)
    embedder = SentenceTransformersEmbedder(
        "stub-model", dimension=2, model=model, torch_module=torch
    )

    vectors = embedder.embed(["legal passage"])

    assert embedder.device == expected_device
    assert embedder.dtype is getattr(torch, expected_dtype)
    assert vectors == [[pytest.approx(0.6), pytest.approx(0.8)]]
    assert model.encode_calls == [
        (
            ["legal passage"],
            {
                "convert_to_numpy": True,
                "normalize_embeddings": False,
                "show_progress_bar": False,
            },
        )
    ]


def test_adapter_validates_configured_dimension() -> None:
    with pytest.raises(ValueError, match="configured dimension is 3"):
        SentenceTransformersEmbedder(
            "stub-model",
            dimension=3,
            model=_ModelStub([[1.0, 0.0]]),
            torch_module=_torch_stub(cuda=False, mps=False),
        )


def test_adapter_passes_selected_device_and_dtype_to_lazy_model_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torch = _torch_stub(cuda=True, mps=True)
    model = _ModelStub([[1.0, 0.0]])
    constructor_calls: list[dict[str, object]] = []

    def construct_model(model_name: str, **kwargs: object) -> _ModelStub:
        constructor_calls.append({"model_name": model_name, **kwargs})
        return model

    monkeypatch.setattr(
        sentence_transformers_adapter.importlib,
        "import_module",
        lambda name: (
            torch if name == "torch" else SimpleNamespace(SentenceTransformer=construct_model)
        ),
    )
    embedder = SentenceTransformersEmbedder("stub-model", dimension=2)

    assert embedder.device == "cuda"
    assert embedder.dtype is torch.float16
    assert constructor_calls == [
        {
            "model_name": "stub-model",
            "device": "cuda",
            "model_kwargs": {"torch_dtype": torch.float16},
        }
    ]


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ([[1.0]], "dimension vector"),
        ([[float("nan"), 1.0]], "non-finite"),
        ([[0.0, 0.0]], "zero-length"),
    ],
)
def test_adapter_rejects_invalid_model_vectors(vectors: list[list[float]], message: str) -> None:
    model = _ModelStub([[0.0, 1.0]])
    embedder = SentenceTransformersEmbedder(
        "stub-model",
        dimension=2,
        model=model,
        torch_module=_torch_stub(cuda=False, mps=False),
    )
    model.vectors = vectors

    with pytest.raises(ValueError, match=message):
        embedder.embed(["legal passage"])


def test_adapter_rejects_wrong_vector_count() -> None:
    model = _ModelStub([[1.0, 0.0]])
    embedder = SentenceTransformersEmbedder(
        "stub-model", dimension=2, model=model, torch_module=_torch_stub(cuda=False, mps=False)
    )
    model.vectors = [[1.0, 0.0], [0.0, 1.0]]

    with pytest.raises(ValueError, match="2 vectors for 1 document inputs"):
        embedder.embed(["only one passage"])
