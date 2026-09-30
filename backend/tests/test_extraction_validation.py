import pytest

from app.schemas.extraction import (
    EntityType,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
    RelationshipType,
)
from app.services.extraction import (
    ExtractionValidationError,
    validate_extraction_result,
)


def entity(entity_id, entity_type, label, evidence, aliases=None):
    return ExtractedEntity(
        id=entity_id,
        type=entity_type,
        label=label,
        canonical_label=label,
        aliases=aliases or [],
        evidence=evidence,
    )


def test_occurrence_threshold_keeps_repeated_entities_and_key_sections() -> None:
    text = (
        "# Nickel leaching study\n"
        "## Introduction\n"
        "Cobalt is mentioned once here.\n"
        "## Conclusions\n"
        "The material is nickel ore."
    )
    result = ExtractionResult(
        entities=[
            entity(
                "process",
                EntityType.PROCESS,
                "Nickel leaching",
                "Nickel leaching study",
            ),
            entity(
                "cobalt",
                EntityType.MATERIAL,
                "Cobalt",
                "Cobalt is mentioned once here.",
            ),
            entity(
                "nickel",
                EntityType.MATERIAL,
                "nickel ore",
                "The material is nickel ore.",
            ),
        ],
        relationships=[],
    )

    validated = validate_extraction_result(result, text, [], minimum_occurrences=2)

    assert {item.id for item in validated.entities} == {"process", "nickel"}


def test_relationship_endpoints_are_retained_even_when_mentioned_once() -> None:
    text = "The leaching process used garnierite."
    result = ExtractionResult(
        entities=[
            entity("process", EntityType.PROCESS, "leaching process", text),
            entity("material", EntityType.MATERIAL, "garnierite", text),
        ],
        relationships=[
            ExtractedRelationship(
                source_id="process",
                target_id="material",
                type=RelationshipType.USES_MATERIAL,
                evidence=text,
            )
        ],
    )

    validated = validate_extraction_result(result, text, [], minimum_occurrences=2)

    assert len(validated.entities) == 2
    assert len(validated.relationships) == 1


def test_unverified_entity_evidence_is_rejected() -> None:
    result = ExtractionResult(
        entities=[
            entity(
                "material",
                EntityType.MATERIAL,
                "nickel",
                "This unsupported statement is not in the source.",
            )
        ],
        relationships=[],
    )

    with pytest.raises(ExtractionValidationError, match="Evidence for entity"):
        validate_extraction_result(result, "The ore contains nickel.", [])


def test_generic_noise_is_filtered() -> None:
    result = ExtractionResult(
        entities=[
            entity(
                "method",
                EntityType.PROCESS,
                "method",
                "The method used nickel ore.",
            )
        ],
        relationships=[],
    )

    validated = validate_extraction_result(
        result, "The method used nickel ore.", [], minimum_occurrences=1
    )

    assert validated.entities == []


def test_canonical_entities_and_relationships_are_deduplicated() -> None:
    text = (
        "# Iron nickel alloy\n"
        "Fe-Ni alloy was used. Iron nickel alloy was used."
    )
    result = ExtractionResult(
        entities=[
            ExtractedEntity(
                id="material-1",
                type=EntityType.MATERIAL,
                label="Fe-Ni alloy",
                canonical_label="Fe-Ni alloy",
                evidence="Fe-Ni alloy was used.",
                aliases=["iron nickel alloy"],
            ),
            ExtractedEntity(
                id="material-2",
                type=EntityType.MATERIAL,
                label="iron nickel alloy",
                canonical_label="Fe-Ni alloy",
                evidence="Iron nickel alloy was used.",
                aliases=["Fe-Ni alloy"],
            ),
        ],
        relationships=[],
    )

    validated = validate_extraction_result(
        result, text, [], minimum_occurrences=2
    )

    assert len(validated.entities) == 1
    assert "Fe-Ni alloy" in validated.entities[0].aliases
    assert "iron nickel alloy" in validated.entities[0].aliases
    assert "Fe-Ni alloy was used." in validated.entities[0].evidence
    assert "Iron nickel alloy was used." in validated.entities[0].evidence


def test_unknown_relationship_endpoint_is_rejected_by_schema() -> None:
    with pytest.raises(ValueError, match="Relationship endpoints"):
        ExtractionResult(
            entities=[entity("process", EntityType.PROCESS, "leaching", "leaching")],
            relationships=[
                ExtractedRelationship(
                    source_id="process",
                    target_id="missing",
                    type=RelationshipType.USES_MATERIAL,
                    evidence="leaching",
                )
            ],
        )
