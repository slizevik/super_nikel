# Neo4j schema

## Node labels

The ontology defines `Material`, `Process`, `Equipment`, `Property`,
`Experiment`, `Publication`, `Document`, `Expert`, `Facility`, `Condition`,
`Country`, and `Claim`.

The current Cypher initialization adds a unique `canonical_label` constraint
for every entity label except `Document`, which has a unique `document_id`
constraint. Initialization and verification scripts live in `docker/neo4j/`.

## Relationships

The application-level contract is in `backend/app/db/ontology.py`:

| Type | Allowed source | Allowed target |
|---|---|---|
| `uses_material` | `Process`, `Experiment` | `Material` |
| `operates_at_condition` | `Process`, `Equipment` | `Condition` |
| `produces_output` | `Process`, `Experiment` | `Property` |
| `described_in` | Any defined type except `Document` | `Document` |
| `validated_by` | `Experiment`, `Claim` | `Expert`, `Publication` |
| `contradicts` | `Claim` | `Claim` |

The extraction schema validates endpoint IDs and allowed endpoint types.
Although Neo4j schema initialization is available, ingestion does not yet
persist extracted entities or relationships to the graph.
