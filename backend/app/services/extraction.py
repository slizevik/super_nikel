import re

from app.core.config import get_settings
from app.schemas.extraction import (
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
    ImageDescription,
)


GENERIC_NOISE = {"исследование", "метод", "результат", "research", "method", "result"}
KEY_SECTION_HEADING = re.compile(
    r"^\s{0,3}#{1,6}\s+.*(?:abstract|аннотац|ключев|conclusion|заключен|вывод|summary|резюме).*$",
    flags=re.IGNORECASE,
)
MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")


class ExtractionValidationError(ValueError):
    pass


def _occurrences(text: str, phrase: str) -> int:
    normalized_phrase = phrase.strip()
    if not normalized_phrase:
        return 0
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return sum(1 for _ in re.finditer(pattern, text, flags=re.IGNORECASE))


def _key_sections(document_text: str) -> str:
    selected: list[str] = []
    current_section_is_key = False
    is_first_heading = True
    for line in document_text.splitlines():
        if MARKDOWN_HEADING.match(line):
            current_section_is_key = is_first_heading or bool(
                KEY_SECTION_HEADING.match(line)
            )
            is_first_heading = False
        if current_section_is_key:
            selected.append(line)
    return "\n".join(selected)


def validate_extraction_result(
    result: ExtractionResult,
    document_text: str,
    image_descriptions: list[ImageDescription],
    minimum_occurrences: int | None = None,
) -> ExtractionResult:
    threshold = minimum_occurrences or get_settings().entity_min_occurrences
    image_evidence = "\n".join(
        f"{description.caption or ''}\n{description.description}\n"
        f"{description.key_information}"
        for description in image_descriptions
        if description.useful
    )
    source_text = f"{document_text}\n{image_evidence}"
    normalized_source = re.sub(r"\s+", " ", source_text).casefold()
    normalized_sections = re.sub(
        r"\s+", " ", _key_sections(document_text)
    ).casefold()
    for relationship in result.relationships:
        evidence = re.sub(r"\s+", " ", relationship.evidence).strip().casefold()
        if evidence not in normalized_source:
            raise ExtractionValidationError(
                "Evidence for a relationship was not found in the parsed "
                "document or useful image descriptions."
            )
    for unclassified in result.unclassified_entities:
        context = re.sub(r"\s+", " ", unclassified.context).strip().casefold()
        if context not in normalized_source:
            raise ExtractionValidationError(
                f"Evidence for unclassified entity '{unclassified.text}' "
                "was not found in the parsed document or useful image descriptions."
            )

    canonical_entities: dict[tuple[str, str], ExtractedEntity] = {}
    original_to_canonical_id: dict[str, str] = {}
    for entity in result.entities:
        evidence = re.sub(r"\s+", " ", entity.evidence).strip().casefold()
        if evidence not in normalized_source:
            raise ExtractionValidationError(
                f"Evidence for entity '{entity.canonical_label}' was not found "
                "in the parsed document or useful image descriptions."
            )

        key = (
            entity.type.value,
            re.sub(r"\s+", " ", entity.canonical_label).strip().casefold(),
        )
        existing = canonical_entities.get(key)
        if existing is None:
            aliases = set(entity.aliases)
            if entity.label.casefold() != entity.canonical_label.casefold():
                aliases.add(entity.label)
            canonical_entities[key] = entity.model_copy(
                update={"aliases": sorted(aliases)}
            )
            original_to_canonical_id[entity.id] = entity.id
        else:
            original_to_canonical_id[entity.id] = existing.id
            aliases = set(existing.aliases)
            aliases.update(entity.aliases)
            if entity.label.casefold() != entity.canonical_label.casefold():
                aliases.add(entity.label)
            evidence_parts = list(
                dict.fromkeys(
                    [
                        *existing.evidence.splitlines(),
                        *entity.evidence.splitlines(),
                    ]
                )
            )
            canonical_entities[key] = existing.model_copy(
                update={
                    "aliases": sorted(aliases),
                    "evidence": "\n".join(evidence_parts)[:2000],
                }
            )

    relationship_entity_ids = {
        original_to_canonical_id[endpoint]
        for relationship in result.relationships
        for endpoint in (relationship.source_id, relationship.target_id)
    }
    retained = []
    for entity in canonical_entities.values():
        if entity.canonical_label.casefold().strip() in GENERIC_NOISE:
            continue
        labels = {entity.canonical_label, entity.label, *entity.aliases}
        occurrence_count = max(
            (_occurrences(source_text, label) for label in labels),
            default=0,
        )
        appears_in_key_section = any(
            _occurrences(normalized_sections, label) > 0 for label in labels
        )
        if (
            occurrence_count >= threshold
            or appears_in_key_section
            or entity.id in relationship_entity_ids
        ):
            retained.append(entity)

    retained_ids = {entity.id for entity in retained}
    relationships_by_key: dict[
        tuple[str, str, str], ExtractedRelationship
    ] = {}
    for relationship in result.relationships:
        source_id = original_to_canonical_id[relationship.source_id]
        target_id = original_to_canonical_id[relationship.target_id]
        if source_id not in retained_ids or target_id not in retained_ids:
            continue
        key = (source_id, target_id, relationship.type.value)
        existing = relationships_by_key.get(key)
        if existing is None:
            relationships_by_key[key] = relationship.model_copy(
                update={"source_id": source_id, "target_id": target_id}
            )
        else:
            evidence_parts = list(
                dict.fromkeys(
                    [
                        *existing.evidence.splitlines(),
                        *relationship.evidence.splitlines(),
                    ]
                )
            )
            relationships_by_key[key] = existing.model_copy(
                update={
                    "evidence": "\n".join(evidence_parts)[:2000],
                }
            )

    return ExtractionResult(
        entities=retained,
        relationships=list(relationships_by_key.values()),
        unclassified_entities=result.unclassified_entities,
    )
