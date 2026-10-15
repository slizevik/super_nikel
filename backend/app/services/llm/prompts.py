ENTITY_EXTRACTION_INSTRUCTIONS = """\
Extract only entities and relationships explicitly supported by the supplied
document. Return one JSON object with exactly these keys:
{
  "entities": [
    {
      "id": "e1",
      "type": "one allowed entity type",
      "label": "source-language label",
      "canonical_label": "canonical name",
      "aliases": [],
      "evidence": "verbatim supporting excerpt"
    }
  ],
  "relationships": [
    {
      "source_id": "e1",
      "target_id": "e2",
      "type": "one allowed relationship type",
      "evidence": "verbatim supporting excerpt"
    }
  ],
  "unclassified_entities": [
    {"text": "entity text", "context": "verbatim surrounding context"}
  ]
}
Always include all three top-level keys: "entities", "relationships", and
"unclassified_entities". Use an empty array when a category has no entries.
Never return an empty object ({}). If no typed entities or relationships can be
supported by the document, return empty arrays and put relevant unclassified
terms in "unclassified_entities"; use three empty arrays only when nothing
relevant is present in the document.
HARD LIMIT: Return no more than 15 entities in the entire "entities" array,
across all entity types combined. This is a maximum, not a target; return fewer
when fewer important entities are supported. Before producing JSON, internally
identify candidate entities, merge aliases and duplicate mentions into one
canonical entity, rank candidates, and keep only the 15 most important.
Prioritize entities that define the article's central subject, are mentioned
frequently across the document, appear in the title, abstract, aims, results,
or conclusions, and are directly needed to explain the main findings. Frequency
is an important signal but must not make generic or incidental terms central.
Exclude passing mentions, generic noise, and entities that do not help explain
the article's main subject or findings. Do not add an entity merely to complete
a relationship. The entity limit counts distinct canonical entities, not
aliases, evidence excerpts, or relationships. Use at most 10 relationships,
only between selected entities. Entity IDs must be unique and every
relationship endpoint must reference an entity in this JSON.
Allowed entity types: Material, Process, Equipment, Property, Experiment,
Publication, Document, Expert, Facility, Condition, Country, Claim.
Use only the listed relationship types and direction:
Process|Experiment -> Material (uses_material);
Process|Equipment -> Condition (operates_at_condition);
Process|Experiment -> Property (produces_output);
any listed type except Document -> Document (described_in);
Experiment|Claim -> Expert|Publication (validated_by);
Claim -> Claim (contradicts).
Do not extract generic noise such as "research", "method", or "result".
Put plausible entities that do not fit the closed type list in
unclassified_entities; never invent an ontology type. Do not infer facts,
authors, countries, dates, or relationships that are not in the source.
Return JSON only.
"""

IMAGE_DESCRIPTION_INSTRUCTIONS = """\
Classify this document image as chart, table, diagram, photo, or other.
For charts, tables, and diagrams, describe the key materials-science facts
that are visibly supported by the image. For other images, state whether the
image is useful for understanding the document; if not, set useful=false and
say so. Do not infer unreadable values. Return JSON only with keys:
image_id, kind, useful, description, key_information, caption.
"""
