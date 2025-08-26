import pandas as pd
import pandera.pandas as pa
from pandera import Check
from pandera.errors import SchemaErrors



# ---------------------------
# Ensembl Schemas
# ---------------------------

# Transcript records from /lookup/id/{gene_id}?expand=1 → data["Transcript"]
ensembl_transcripts_schema = pa.DataFrameSchema(
    {
        "id": pa.Column(pa.String),
        "biotype": pa.Column(pa.String, nullable=True),
        "start": pa.Column(pa.Int64, nullable=True, coerce=True),
        "end": pa.Column(pa.Int64, nullable=True, coerce=True),
        "strand": pa.Column(pa.Int64, nullable=True, coerce=True),
    },
    strict=False,
)


# Variation mappings from /variation/{species}/{variant_id} → data["mappings"]
ensembl_variation_mappings_schema = pa.DataFrameSchema(
    {
        "seq_region_name": pa.Column(pa.String),
        "start": pa.Column(pa.Int64, coerce=True),
        "end": pa.Column(pa.Int64, coerce=True),
        "strand": pa.Column(pa.Int64, coerce=True),
        "allele_string": pa.Column(pa.String),
    },
    strict=False,
)



# Gene annotation (from /lookup/id/{id} when normalised to a single-row frame)
ensembl_gene_annotation_schema = pa.DataFrameSchema(
    {
        "id": pa.Column(pa.String),
        "display_name": pa.Column(pa.String, nullable=True),
        "biotype": pa.Column(pa.String, nullable=True),
        "seq_region_name": pa.Column(pa.String, nullable=True),
        "start": pa.Column(pa.Int64, nullable=True, coerce=True),
        "end": pa.Column(pa.Int64, nullable=True, coerce=True),
        "strand": pa.Column(pa.Int64, nullable=True, coerce=True),
    },
    strict=False,
)


# Variant summary (top-level fields from /variation/{species}/{variant_id},
# represented as a single-row frame after json_normalize)
ensembl_variant_summary_schema = pa.DataFrameSchema(
    {
        "id": pa.Column(pa.String, nullable=True),
        "most_severe_consequence": pa.Column(pa.String, nullable=True),
        "minor_allele": pa.Column(pa.String, nullable=True),
        "minor_allele_freq": pa.Column(pa.Float64, Check.in_range(0.0, 1.0), nullable=True),
    },
    strict=False,
)


# Orthologs (from /homology/id/{gene}?type=orthologues -> data[0].homologies)
# After flattening with pandas.json_normalize on "homologies",
# common fields include: type, target.id, target.species, target.perc_id, target.perc_pos
ensembl_orthologs_schema = pa.DataFrameSchema(
    {
        "type": pa.Column(pa.String, nullable=True),
        "target.id": pa.Column(pa.String, nullable=True),
        "target.species": pa.Column(pa.String, nullable=True),
        "target.perc_id": pa.Column(pa.Float64, Check.in_range(0.0, 100.0), nullable=True),
        "target.perc_pos": pa.Column(pa.Float64, Check.in_range(0.0, 100.0), nullable=True),
    },
    strict=False,
)


