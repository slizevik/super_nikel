import pytest

from app.db.ontology import (
    EntityType,
    RELATIONSHIP_DEFINITIONS,
    RelationshipType,
    validate_relationship,
)


def test_all_ontology_relationships_have_endpoint_definitions() -> None:
    assert set(RELATIONSHIP_DEFINITIONS) == set(RelationshipType)


@pytest.mark.parametrize(
    ("relationship", "source", "target"),
    [
        (
            RelationshipType.USES_MATERIAL,
            EntityType.EXPERIMENT,
            EntityType.MATERIAL,
        ),
        (
            RelationshipType.OPERATES_AT_CONDITION,
            EntityType.EQUIPMENT,
            EntityType.CONDITION,
        ),
        (
            RelationshipType.PRODUCES_OUTPUT,
            EntityType.PROCESS,
            EntityType.PROPERTY,
        ),
        (
            RelationshipType.DESCRIBED_IN,
            EntityType.CLAIM,
            EntityType.DOCUMENT,
        ),
        (
            RelationshipType.VALIDATED_BY,
            EntityType.EXPERIMENT,
            EntityType.EXPERT,
        ),
        (
            RelationshipType.CONTRADICTS,
            EntityType.CLAIM,
            EntityType.CLAIM,
        ),
    ],
)
def test_valid_relationship_endpoints(
    relationship: RelationshipType, source: EntityType, target: EntityType
) -> None:
    validate_relationship(relationship, source, target)


def test_invalid_relationship_endpoints_are_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid endpoints for uses_material"):
        validate_relationship(
            RelationshipType.USES_MATERIAL,
            EntityType.EQUIPMENT,
            EntityType.MATERIAL,
        )
