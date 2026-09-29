from dataclasses import dataclass
from enum import StrEnum


class EntityType(StrEnum):
    MATERIAL = "Material"
    PROCESS = "Process"
    EQUIPMENT = "Equipment"
    PROPERTY = "Property"
    EXPERIMENT = "Experiment"
    PUBLICATION = "Publication"
    DOCUMENT = "Document"
    EXPERT = "Expert"
    FACILITY = "Facility"
    CONDITION = "Condition"
    COUNTRY = "Country"
    CLAIM = "Claim"


class RelationshipType(StrEnum):
    USES_MATERIAL = "uses_material"
    OPERATES_AT_CONDITION = "operates_at_condition"
    PRODUCES_OUTPUT = "produces_output"
    DESCRIBED_IN = "described_in"
    VALIDATED_BY = "validated_by"
    CONTRADICTS = "contradicts"


@dataclass(frozen=True)
class RelationshipDefinition:
    sources: frozenset[EntityType]
    targets: frozenset[EntityType]


RELATIONSHIP_DEFINITIONS = {
    RelationshipType.USES_MATERIAL: RelationshipDefinition(
        sources=frozenset({EntityType.PROCESS, EntityType.EXPERIMENT}),
        targets=frozenset({EntityType.MATERIAL}),
    ),
    RelationshipType.OPERATES_AT_CONDITION: RelationshipDefinition(
        sources=frozenset({EntityType.PROCESS, EntityType.EQUIPMENT}),
        targets=frozenset({EntityType.CONDITION}),
    ),
    RelationshipType.PRODUCES_OUTPUT: RelationshipDefinition(
        sources=frozenset({EntityType.PROCESS, EntityType.EXPERIMENT}),
        targets=frozenset({EntityType.PROPERTY}),
    ),
    RelationshipType.DESCRIBED_IN: RelationshipDefinition(
        sources=frozenset(set(EntityType) - {EntityType.DOCUMENT}),
        targets=frozenset({EntityType.DOCUMENT}),
    ),
    RelationshipType.VALIDATED_BY: RelationshipDefinition(
        sources=frozenset({EntityType.EXPERIMENT, EntityType.CLAIM}),
        targets=frozenset({EntityType.EXPERT, EntityType.PUBLICATION}),
    ),
    RelationshipType.CONTRADICTS: RelationshipDefinition(
        sources=frozenset({EntityType.CLAIM}),
        targets=frozenset({EntityType.CLAIM}),
    ),
}


def validate_relationship(
    relationship: RelationshipType,
    source: EntityType,
    target: EntityType,
) -> None:
    definition = RELATIONSHIP_DEFINITIONS[relationship]
    if source not in definition.sources or target not in definition.targets:
        allowed_pairs = ", ".join(
            f"{source_type.value} -> {target_type.value}"
            for source_type in sorted(
                definition.sources, key=lambda entity_type: entity_type.value
            )
            for target_type in sorted(
                definition.targets, key=lambda entity_type: entity_type.value
            )
        )
        raise ValueError(
            f"Invalid endpoints for {relationship.value}: "
            f"{source.value} -> {target.value}; allowed: {allowed_pairs}"
        )
