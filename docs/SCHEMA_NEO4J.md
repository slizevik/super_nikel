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
The backend has an async Bolt client and repository for idempotent entity,
relationship, and document-provenance writes, plus reads by canonical label,
document ID, or source document. Entity nodes use `canonical_label` as their
unique key. The current extraction contract supplies `name`, `label`,
`aliases`, and `evidence`; `source_document_id` and `source_documents` track
provenance. Each entity is
linked to its source `Document` with `described_in`, whose relationship also
stores the evidence for that document.

The ingestion pipeline does not yet call the repository. Extracted results are
still stored in PostgreSQL and jobs stop at `awaiting_persistence`.
