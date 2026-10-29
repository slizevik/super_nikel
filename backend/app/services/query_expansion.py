import re


_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "article",
    "articles",
    "be",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "paper",
    "papers",
    "the",
    "their",
    "to",
    "use",
    "used",
    "uses",
    "using",
    "was",
    "were",
    "what",
    "which",
    "with",
}
_DATASET_TERMS = {
    "dataset",
    "datasets",
}
_DATASET_PHRASES = {
    ("data", "set"),
    ("data", "sets"),
    ("training", "set"),
    ("training", "sets"),
    ("validation", "set"),
    ("validation", "sets"),
    ("test", "set"),
    ("test", "sets"),
}
_DATASET_EXPANSIONS = (
    "dataset",
    "datasets",
    "data set",
    "data sets",
    "benchmark",
    "benchmarks",
    "training set",
    "training sets",
    "validation set",
    "validation sets",
    "test set",
    "test sets",
    "cohort",
    "cohorts",
)


def build_expanded_tsquery(question: str) -> str:
    """Build a safe PostgreSQL tsquery from English keywords and known aliases."""
    words = re.findall(r"[a-z0-9]+", question.lower())
    keywords = [word for word in words if len(word) > 2 and word not in _STOP_WORDS]
    phrases = []
    adjacent_words = {
        tuple(words[index : index + 2])
        for index in range(len(words) - 1)
    }
    if _DATASET_TERMS.intersection(words) or _DATASET_PHRASES.intersection(
        adjacent_words
    ):
        phrases.extend(_DATASET_EXPANSIONS)

    clauses: list[str] = []
    for phrase in [*keywords, *phrases]:
        terms = re.findall(r"[a-z0-9]+", phrase.lower())
        if terms:
            clause = " & ".join(terms)
            if clause not in clauses:
                clauses.append(clause)
    return " | ".join(clauses)


def contains_cyrillic(value: str) -> bool:
    return re.search(r"[\u0400-\u04ff]", value) is not None
