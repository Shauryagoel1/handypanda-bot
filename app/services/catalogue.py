# app/services/catalogue.py

import os
import re
from numpy.linalg import norm
import numpy as np
from sentence_transformers import SentenceTransformer
from flask import current_app

from app.services import sheets   # <-- new import for Google-Sheets loader

# In-memory state
_catalogue   = []
_model       = None
_embeddings  = None
_ITEM_TYPES  = None


def load_catalogue():
    """
    Loads the Catalogue tab via sheets.load_catalogue_df(), normalises
    columns, builds sentence-transformer embeddings, caches item-type set.
    """
    global _catalogue, _model, _embeddings, _ITEM_TYPES

    df = sheets.load_catalogue_df()        # <-- fresh DataFrame incl. SKU_IDs

    required = ['SKU_ID', 'SKU', 'ProductName', 'Brand',
                'DimScheme', 'SizeText', 'DimA', 'DimB',
                'DimUnit', 'PriceUnit', 'SellingPrice']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Catalogue missing columns: {missing}")

    _catalogue = []
    texts      = []

    for _, row in df.iterrows():
        p = {
            'id'         : str(row['SKU_ID']).strip(),
            'sku'        : str(row['SKU']).strip(),
            'name'       : str(row['ProductName']).strip(),
            'brand'      : str(row['Brand']).strip(),
            'scheme'     : str(row['DimScheme']).strip().upper(),
            'size_text'  : str(row['SizeText']).strip(),
            'dim_a'      : float(row.get('DimA', 0) or 0),
            'dim_b'      : float(row.get('DimB', 0) or 0),
            'unit'       : str(row.get('DimUnit', 'mm')).strip(),
            'price_unit' : str(row.get('PriceUnit', 'PCS')).strip(),
            'price'      : float(row['SellingPrice'])
        }
        _catalogue.append(p)
        texts.append(" ".join(filter(None, [
            p['brand'], p['name'], p['size_text']
        ])))

    # Embeddings
    # _model      = SentenceTransformer('all-MiniLM-L6-v2')
    _model      = SentenceTransformer("paraphrase-MiniLM-L3-v2")
    _embeddings = _model.encode(texts, convert_to_numpy=True)

    _ITEM_TYPES = set(p['name'].lower() for p in _catalogue)


# -------- Dimension / scheme distance helpers ----------

def _parse_query_dims(q: str):
    """
    Returns (nums:list[float], unit:str or 'mm').
    Accepts '110 mm', '110x75', '8 x 4 ft', etc.
    """
    cleaned = q.lower().replace('×', 'x').replace('*', 'x')
    unit = 'mm'
    if any(u in cleaned for u in ['inch', '"']): unit = 'inch'
    if 'ft' in cleaned or 'feet' in cleaned:     unit = 'ft'
    nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', cleaned)]
    return nums, unit


def _unit_to_mm(val: float, unit: str):
    if unit == 'inch': return val * 25.4
    if unit == 'ft':   return val * 304.8
    return val


def _scheme_distance(p, q_nums, q_unit):
    """
    Numeric distance between product p and query numbers.
    Large fallback (999) if not comparable.
    """
    if not q_nums:
        return 999

    scheme = p['scheme']
    a, b = p['dim_a'], p['dim_b']
    q_nums_mm = [_unit_to_mm(n, q_unit) for n in q_nums]

    if scheme == 'OD':
        return abs(a - q_nums_mm[0])
    if scheme == 'ODxOD' and len(q_nums_mm) >= 2:
        d1 = abs(a - q_nums_mm[0]) + abs(b - q_nums_mm[1])
        d2 = abs(a - q_nums_mm[1]) + abs(b - q_nums_mm[0])
        return min(d1, d2)
    if scheme == 'LxW' and len(q_nums_mm) >= 2:
        d1 = abs(a - q_nums_mm[0]) + abs(b - q_nums_mm[1])
        d2 = abs(a - q_nums_mm[1]) + abs(b - q_nums_mm[0])
        return min(d1, d2)
    if scheme in ('CS','VOL'):
        return abs(a - q_nums_mm[0])
    return 999


# -------- Main search entrypoint ----------

def enhanced_search(query: str, top_n: int = 3):
    """
    Combines item-type matching, semantic similarity, and size distance
    using the DimScheme logic.
    """
    global _catalogue, _model, _embeddings, _ITEM_TYPES
    if not _catalogue:
        load_catalogue()

    q_low   = query.lower()
    q_embed = _model.encode(query, convert_to_numpy=True)

    # Item-type match (plural-aware)
    matched_types = [t for t in _ITEM_TYPES if re.search(rf'\b{re.escape(t)}s?\b', q_low)]

    # Parse numbers
    q_nums, q_unit = _parse_query_dims(query)

    def combined_score(p, sem):
        dist = _scheme_distance(p, q_nums, q_unit)
        return sem - 0.01 * dist

    if matched_types:
        cand_idx = [i for i, p in enumerate(_catalogue) if p['name'].lower() in matched_types]
    else:
        cand_idx = range(len(_catalogue))

    # Compute semantic similarity
    sem_sims = (_embeddings[cand_idx] @ q_embed) / (norm(_embeddings[cand_idx], axis=1) * norm(q_embed))
    scored = []
    for idx, sem in zip(cand_idx, sem_sims):
        p = _catalogue[idx]
        score = combined_score(p, sem)
        scored.append((score, p))

    ranked = [p for _, p in sorted(scored, key=lambda x: x[0], reverse=True)]
    return ranked[:top_n]
