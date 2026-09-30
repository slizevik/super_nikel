from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.ontology import EntityType, RelationshipType, validate_relationship


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedEntity(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: EntityType
    label: str = Field(min_length=1, max_length=300)
    canonical_label: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    evidence: str = Field(min_length=1, max_length=2000)


class ExtractedRelationship(StrictSchema):
    source_id: str = Field(min_length=1, max_length=80)
    target_id: str = Field(min_length=1, max_length=80)
    type: RelationshipType
    evidence: str = Field(min_length=1, max_length=2000)


class UnclassifiedEntity(StrictSchema):
    text: str = Field(min_length=1, max_length=300)
    context: str = Field(min_length=1, max_length=2000)


class ExtractionResult(StrictSchema):
    entities: list[ExtractedEntity] = Field(max_length=60)
    relationships: list[ExtractedRelationship] = Field(max_length=10)
    unclassified_entities: list[UnclassifiedEntity] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph_contract(self) -> "ExtractionResult":
        ids: set[str] = set()
        by_id: dict[str, ExtractedEntity] = {}
        counts: dict[EntityType, int] = {}
        for entity in self.entities:
            if entity.id in ids:
                raise ValueError(f"Duplicate entity id: {entity.id}")
            ids.add(entity.id)
            by_id[entity.id] = entity
            counts[entity.type] = counts.get(entity.type, 0) + 1
        over_limit = [entity_type.value for entity_type, count in counts.items() if count > 5]
        if over_limit:
            raise ValueError(
                "At most 5 entities per type are allowed; exceeded: "
                + ", ".join(sorted(over_limit))
            )
        for relationship in self.relationships:
            source = by_id.get(relationship.source_id)
            target = by_id.get(relationship.target_id)
            if source is None or target is None:
                raise ValueError(
                    "Relationship endpoints must reference entities in this result."
                )
            validate_relationship(relationship.type, source.type, target.type)
        return self


from enum import StrEnum


class ImageKind(StrEnum):
    CHART = "chart"
    TABLE = "table"
    DIAGRAM = "diagram"
    PHOTO = "photo"
    OTHER = "other"


class ImageDescription(StrictSchema):
    image_id: str = Field(min_length=1, max_length=80)
    kind: ImageKind
    useful: bool
    description: str = Field(max_length=4000)
    key_information: str = Field(default="", max_length=4000)
    caption: str | None = Field(default=None, max_length=1000)
