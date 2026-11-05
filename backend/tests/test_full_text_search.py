from app.services.full_text_search import build_full_text_queries


def test_build_full_text_queries_returns_lexical_variants() -> None:
    original, translated, expanded = build_full_text_queries(
        "Какие датасеты использовались?",
        "Which datasets were used?",
    )

    assert original is not None
    assert translated is not None
    assert expanded is not None


def test_build_full_text_queries_without_translation_stays_valid() -> None:
    original, translated, expanded = build_full_text_queries("RNALocate dataset")

    assert original is not None
    assert translated is not None
    assert expanded is not None
