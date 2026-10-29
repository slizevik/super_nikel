from app.services.query_expansion import (
    build_expanded_tsquery,
    contains_cyrillic,
)


def test_dataset_question_expands_to_common_research_terms() -> None:
    query = build_expanded_tsquery("Which datasets were used for training?")

    assert "dataset" in query
    assert "datasets" in query
    assert "benchmark" in query
    assert "training & set" in query
    assert "used" not in query
    assert "which" not in query


def test_non_dataset_question_keeps_only_content_words() -> None:
    query = build_expanded_tsquery("Which model was used for localization?")

    assert query == "model | localization"


def test_cyrillic_question_detection() -> None:
    assert contains_cyrillic("Какие датасеты использовались?")
    assert not contains_cyrillic("Which datasets were used?")
