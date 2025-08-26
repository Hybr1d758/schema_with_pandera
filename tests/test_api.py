import json
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_gene_annotation(monkeypatch):
    async def fake_get(path, params=None):
        return {
            "id": "ENSG00000139618",
            "display_name": "BRCA2",
            "biotype": "protein_coding",
            "seq_region_name": "13",
            "start": 32315474,
            "end": 32400266,
            "strand": 1,
        }

    monkeypatch.setattr("app.main._ensembl_get", fake_get)
    resp = client.get("/ensembl/gene-annotation", params={"gene_id": "ENSG00000139618"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_gene_transcripts(monkeypatch):
    async def fake_get(path, params=None):
        return {
            "Transcript": [
                {"id": "ENST0001", "biotype": "protein_coding", "start": 1, "end": 10, "strand": 1},
                {"id": "ENST0002", "biotype": "lncRNA", "start": 20, "end": 40, "strand": -1},
            ]
        }

    monkeypatch.setattr("app.main._ensembl_get", fake_get)
    resp = client.get("/ensembl/gene-transcripts", params={"species": "human", "gene_id": "ENSGX"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True


def test_variation(monkeypatch):
    async def fake_get(path, params=None):
        return {
            "name": "rs699",
            "most_severe_consequence": "missense_variant",
            "minor_allele": "T",
            "minor_allele_freq": 0.4,
            "mappings": [
                {
                    "seq_region_name": "1",
                    "start": 230710048,
                    "end": 230710048,
                    "strand": 1,
                    "allele_string": "A/T",
                }
            ],
        }

    monkeypatch.setattr("app.main._ensembl_get", fake_get)
    resp = client.get("/ensembl/variation", params={"species": "human", "variant_id": "rs699"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["valid"] is True
    assert data["mappings"]["valid"] is True


def test_orthologs(monkeypatch):
    async def fake_get(path, params=None):
        return {
            "data": [
                {
                    "homologies": [
                        {
                            "type": "ortholog_one2one",
                            "target": {
                                "id": "ENSMUSG00000017146",
                                "species": "mouse",
                                "perc_id": 85.0,
                                "perc_pos": 90.0,
                            },
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr("app.main._ensembl_get", fake_get)
    resp = client.get("/ensembl/orthologs", params={"gene_id": "ENSGX", "target_species": "mouse"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True


