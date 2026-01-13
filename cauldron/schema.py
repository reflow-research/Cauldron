"""Schema hashing utilities for Frostbite manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import re

SCHEMA_IDS = {
    "vector": 0,
    "time_series": 1,
    "graph": 2,
    "custom": 3,
}


def _fnv1a32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFF_FFFF
    return h


def _canonical_schema(manifest: Dict[str, Any]) -> Dict[str, Any]:
    schema = manifest.get("schema")
    if not isinstance(schema, dict):
        raise ValueError("schema table missing")
    schema_type = schema.get("type")
    if schema_type not in SCHEMA_IDS:
        raise ValueError("schema.type must be vector, time_series, graph, or custom")

    out: Dict[str, Any] = {"type": schema_type}

    if schema_type == "vector":
        s = schema.get("vector", {})
        out["input_dtype"] = s.get("input_dtype")
        out["input_shape"] = s.get("input_shape")
        out["output_dtype"] = s.get("output_dtype")
        out["output_shape"] = s.get("output_shape")
    elif schema_type == "time_series":
        s = schema.get("time_series", {})
        out["input_dtype"] = s.get("input_dtype")
        out["window"] = s.get("window")
        out["features"] = s.get("features")
        out["stride"] = s.get("stride", 1)
        out["output_dtype"] = s.get("output_dtype")
        out["output_shape"] = s.get("output_shape")
    elif schema_type == "graph":
        s = schema.get("graph", {})
        out["input_dtype"] = s.get("input_dtype")
        out["node_feature_dim"] = s.get("node_feature_dim")
        out["edge_feature_dim"] = s.get("edge_feature_dim")
        out["max_nodes"] = s.get("max_nodes")
        out["max_edges"] = s.get("max_edges")
        out["output_dtype"] = s.get("output_dtype")
        out["output_shape"] = s.get("output_shape")
    elif schema_type == "custom":
        s = schema.get("custom", {})
        out["input_blob_size"] = s.get("input_blob_size")
        out["output_blob_size"] = s.get("output_blob_size")
        out["alignment"] = s.get("alignment")
        fields = s.get("fields")
        if isinstance(fields, list):
            field_list: List[Dict[str, Any]] = []
            for f in fields:
                if not isinstance(f, dict):
                    continue
                field_list.append(
                    {
                        "name": f.get("name"),
                        "offset": f.get("offset"),
                        "dtype": f.get("dtype"),
                        "shape": f.get("shape"),
                    }
                )
            field_list.sort(key=lambda item: (item.get("offset") or 0, item.get("name") or ""))
            out["fields"] = field_list

    return out


def schema_hash32(manifest: Dict[str, Any]) -> int:
    canonical = _canonical_schema(manifest)
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fnv1a32(payload)


def format_hash32(value: int) -> str:
    return f"0x{value:08X}"


def parse_hash32(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError("schema hash must be a string")
    if not (value.startswith("0x") and len(value) == 10):
        raise ValueError("schema hash must be 32-bit hex (0xXXXXXXXX)")
    return int(value, 16)


def update_manifest_schema_hash(manifest_path: Path, hash_str: str) -> None:
    text = manifest_path.read_text()
    lines = text.splitlines()
    out: List[str] = []
    in_custom = False
    inserted = False
    indent = ""

    for line in lines:
        if re.match(r"^\s*\[schema\.custom\]\s*$", line):
            in_custom = True
            out.append(line)
            continue

        if in_custom and re.match(r"^\s*\[", line):
            if not inserted:
                out.append(f"{indent}schema_hash32 = \"{hash_str}\"")
                inserted = True
            in_custom = False
            out.append(line)
            continue

        if in_custom:
            key_match = re.match(r"^(\s*)schema_hash32\s*=", line)
            if key_match:
                indent = key_match.group(1)
                out.append(f"{indent}schema_hash32 = \"{hash_str}\"")
                inserted = True
                continue
            if indent == "":
                indent_match = re.match(r"^(\s*)[A-Za-z0-9_]+\s*=", line)
                if indent_match:
                    indent = indent_match.group(1)

        out.append(line)

    if in_custom and not inserted:
        out.append(f"{indent}schema_hash32 = \"{hash_str}\"")
        inserted = True

    if not inserted:
        raise ValueError("schema.custom table not found in manifest")

    trailing = "\n" if text.endswith("\n") else ""
    manifest_path.write_text("\n".join(out) + trailing)
