from typing import Any, Dict, List, Optional

import asyncio
import os
import logging
import hashlib
import json
import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from starlette.middleware.base import BaseHTTPMiddleware

from app.schema import (
    ensembl_transcripts_schema,
    ensembl_gene_annotation_schema,
    ensembl_variant_summary_schema,
    ensembl_variation_mappings_schema,
    ensembl_orthologs_schema,
)


app = FastAPI(title="Pandera Validator API", version="0.4.0")


# -------- Logging setup (structured JSON lines) --------
logger = logging.getLogger("pandera_ensembl")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(message)s")  # we emit JSON strings
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = asyncio.get_event_loop().time()
        response = await call_next(request)
        duration_ms = (asyncio.get_event_loop().time() - start) * 1000
        # Structured log (JSON)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
            # If a client sends X-Request-ID, include it for correlation
            "request_id": request.headers.get("x-request-id"),
        }))
        return response


app.add_middleware(RequestTimingMiddleware)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "message": "Pandera Validator API",
        "endpoints": "/ensembl/gene-annotation, /ensembl/gene-transcripts, /ensembl/variation, /ensembl/orthologs",
    }


# ---------------------------
# Ensembl REST helpers & endpoints
# ---------------------------

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


ENSEMBL_REST = os.getenv("ENSEMBL_BASE_URL", "https://rest.ensembl.org")
DEFAULT_TIMEOUT_SECONDS = _env_float("ENSEMBL_TIMEOUT_SECONDS", 30.0)
DEFAULT_CACHE_TTL_SECONDS = _env_float("ENSEMBL_CACHE_TTL_SECONDS", 30.0)
DEFAULT_RETRIES = _env_int("ENSEMBL_RETRIES", 3)


@app.on_event("startup")
async def _startup() -> None:
    app.state.http = httpx.AsyncClient(
        base_url=ENSEMBL_REST,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    app.state.cache: Dict[str, Dict[str, Any]] = {}
    app.state.retries = DEFAULT_RETRIES
    app.state.cache_ttl = DEFAULT_CACHE_TTL_SECONDS


@app.on_event("shutdown")
async def _shutdown() -> None:
    client: httpx.AsyncClient = app.state.http
    await client.aclose()


def _cache_key(path: str, params: Optional[Dict[str, Any]]) -> str:
    payload = json.dumps({"path": path, "params": params or {}}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def _ensembl_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # simple TTL cache
    key = _cache_key(path, params)
    entry = app.state.cache.get(key)
    if entry and entry["expires_at"] > asyncio.get_event_loop().time():
        return entry["data"]

    # retries on transient errors
    last_exc: Optional[Exception] = None
    for attempt in range(int(app.state.retries)):
        try:
            resp = await app.state.http.get(path, params=params or {})
            if resp.status_code >= 500:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            if resp.status_code >= 400:
                # client error -> no retry
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()
            app.state.cache[key] = {
                "data": data,
                "expires_at": asyncio.get_event_loop().time() + float(app.state.cache_ttl),
            }
            return data
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            last_exc = exc
            await asyncio.sleep(0.2 * (attempt + 1))  # backoff
    # if we exhausted retries
    if last_exc is not None:
        raise HTTPException(status_code=502, detail=f"Upstream error: {last_exc}")
    raise HTTPException(status_code=502, detail="Unknown upstream error")


@app.get("/ensembl/gene-transcripts")
async def ensembl_gene_transcripts(
    species: str = Query(..., description="Species e.g. human, mouse"),
    gene_id: str = Query(..., description="Stable gene ID e.g. ENSG00000139618"),
) -> Dict[str, Any]:
    data = await _ensembl_get(f"/lookup/id/{gene_id}", params={"expand": 1})
    transcripts = [t for t in data.get("Transcript", [])]
    df = pd.DataFrame.from_records(transcripts)
    try:
        ensembl_transcripts_schema.validate(df, lazy=True)
        valid = True
        errors: List[Dict[str, Any]] = []
    except Exception as err:  # pragma: no cover
        valid = False
        errors = [{"error": str(err)}]
    return {"valid": valid, "num_rows": int(df.shape[0]), "num_columns": int(df.shape[1]), "errors": errors}


@app.get("/ensembl/gene-annotation")
async def ensembl_gene_annotation(
    gene_id: str = Query(..., description="Stable gene ID e.g. ENSG00000139618"),
) -> Dict[str, Any]:
    data = await _ensembl_get(f"/lookup/id/{gene_id}")
    df = pd.json_normalize(data)
    try:
        ensembl_gene_annotation_schema.validate(df, lazy=True)
        valid = True
        errors: List[Dict[str, Any]] = []
    except Exception as err:  # pragma: no cover
        valid = False
        errors = [{"error": str(err)}]
    return {"valid": valid, "num_rows": int(df.shape[0]), "num_columns": int(df.shape[1]), "errors": errors}


@app.get("/ensembl/variation")
async def ensembl_variation(
    species: str = Query(..., description="Species e.g. human"),
    variant_id: str = Query(..., description="Variant ID e.g. rs699"),
) -> Dict[str, Any]:
    data = await _ensembl_get(f"/variation/{species}/{variant_id}")
    # Summary (single-row)
    df_summary = pd.json_normalize({
        "id": data.get("name") or data.get("id"),
        "most_severe_consequence": data.get("most_severe_consequence"),
        "minor_allele": data.get("minor_allele"),
        "minor_allele_freq": data.get("minor_allele_freq"),
    })
    # Mappings
    mappings = data.get("mappings", [])
    df_map = pd.json_normalize(mappings)

    summary_result: Dict[str, Any]
    mappings_result: Dict[str, Any]

    # Validate summary
    try:
        ensembl_variant_summary_schema.validate(df_summary, lazy=True)
        summary_result = {"valid": True, "num_rows": int(df_summary.shape[0]), "num_columns": int(df_summary.shape[1]), "errors": []}
    except Exception as err:  # pragma: no cover
        summary_result = {"valid": False, "num_rows": int(df_summary.shape[0]), "num_columns": int(df_summary.shape[1]), "errors": [{"error": str(err)}]}

    # Validate mappings (allow empty)
    if df_map.empty:
        mappings_result = {"valid": True, "num_rows": 0, "num_columns": 0, "errors": []}
    else:
        try:
            ensembl_variation_mappings_schema.validate(df_map, lazy=True)
            mappings_result = {"valid": True, "num_rows": int(df_map.shape[0]), "num_columns": int(df_map.shape[1]), "errors": []}
        except Exception as err:  # pragma: no cover
            mappings_result = {"valid": False, "num_rows": int(df_map.shape[0]), "num_columns": int(df_map.shape[1]), "errors": [{"error": str(err)}]}

    return {"summary": summary_result, "mappings": mappings_result}


@app.get("/ensembl/orthologs")
async def ensembl_orthologs(
    gene_id: str = Query(..., description="Stable gene ID e.g. ENSG00000139618"),
    target_species: Optional[str] = Query(None, description="Optional species filter, e.g. mouse"),
) -> Dict[str, Any]:
    data = await _ensembl_get(f"/homology/id/{gene_id}", params={"type": "orthologues"})
    items = data.get("data", [])
    homologies = items[0].get("homologies", []) if items else []
    df = pd.json_normalize(homologies)
    if target_species:
        df = df[df.get("target.species").eq(target_species)]
    try:
        ensembl_orthologs_schema.validate(df, lazy=True)
        valid = True
        errors: List[Dict[str, Any]] = []
    except Exception as err:  # pragma: no cover
        valid = False
        errors = [{"error": str(err)}]
    return {"valid": valid, "num_rows": int(df.shape[0]), "num_columns": int(df.shape[1]), "errors": errors}


@app.get("/ensembl/variation")
def ensembl_variation(
    species: str = Query(..., description="Species e.g. human"),
    variant_id: str = Query(..., description="Variant ID e.g. rs699"),
) -> Dict[str, Any]:
    data = _ensembl_get(f"/variation/{species}/{variant_id}")
    # Flatten consequence terms
    cons = data.get("most_severe_consequence")
    mappings = data.get("mappings", [])
    df = pd.json_normalize(mappings)
    from pandera import Column
    import pandera.pandas as pa
    schema = pa.DataFrameSchema(
        {
            "seq_region_name": pa.Column(pa.String),
            "start": pa.Column(pa.Int64, coerce=True),
            "end": pa.Column(pa.Int64, coerce=True),
            "strand": pa.Column(pa.Int64, coerce=True),
            "allele_string": pa.Column(pa.String),
        },
        strict=False,
    )
    try:
        schema.validate(df, lazy=True)
        valid = True
        errors: List[Dict[str, Any]] = []
    except Exception as err:  # pragma: no cover
        valid = False
        errors = [{"error": str(err)}]
    return {
        "valid": valid,
        "num_rows": int(df.shape[0]),
        "num_columns": int(df.shape[1]),
        "errors": errors,
        "most_severe_consequence": cons,
    }


