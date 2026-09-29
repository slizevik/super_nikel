SHOW CONSTRAINTS
YIELD name
WHERE name IN [
    'material_canonical_label_unique',
    'process_canonical_label_unique',
    'equipment_canonical_label_unique',
    'property_canonical_label_unique',
    'experiment_canonical_label_unique',
    'publication_canonical_label_unique',
    'expert_canonical_label_unique',
    'facility_canonical_label_unique',
    'condition_canonical_label_unique',
    'country_canonical_label_unique',
    'claim_canonical_label_unique',
    'document_document_id_unique'
]
RETURN count(name) AS ontology_constraint_count;
