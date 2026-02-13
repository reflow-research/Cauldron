"""Conversion helpers for finance-int models."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import struct
from typing import Any, Dict, List, Tuple


Q16 = 1 << 16


@dataclass
class LinearResult:
    scale_q16: int


@dataclass
class MlpResult:
    w1_scale_q16: int
    w2_scale_q16: int


@dataclass
class TwoTowerResult:
    w1_scale_q16: int
    w2_scale_q16: int


@dataclass
class Mlp2Result:
    w1_scale_q16: int
    w2_scale_q16: int
    w3_scale_q16: int


@dataclass
class Mlp3Result:
    w1_scale_q16: int
    w2_scale_q16: int
    w3_scale_q16: int
    w4_scale_q16: int


@dataclass
class CnnResult:
    w1_scale_q16: int
    w2_scale_q16: int


def _coerce_mapping(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        if "state_dict" in data and isinstance(data["state_dict"], dict):
            data = data["state_dict"]
        return {k: _as_list(v) for k, v in data.items()}
    if hasattr(data, "state_dict"):
        return {k: _as_list(v) for k, v in data.state_dict().items()}
    if hasattr(data, "tolist"):
        return {"w": data}
    raise ValueError("Unsupported input object; expected dict or tensor")


def _load_input(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text())
    if suffix == ".npz":
        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise ImportError("numpy is required to load .npz files") from exc
        data = np.load(path)
        return {k: data[k] for k in data.files}
    if suffix == ".npy":
        try:
            import numpy as np  # type: ignore
        except ImportError as exc:
            raise ImportError("numpy is required to load .npy files") from exc
        arr = np.load(path)
        return {"w": arr}
    if suffix in (".pt", ".pth"):
        try:
            import torch  # type: ignore
        except ImportError as exc:
            raise ImportError("torch is required to load .pt/.pth files") from exc
        data = torch.load(path, map_location="cpu")
        return _coerce_mapping(data)
    if suffix == ".safetensors":
        try:
            from safetensors import safe_open  # type: ignore
        except ImportError as exc:
            raise ImportError("safetensors is required to load .safetensors files") from exc
        out: Dict[str, Any] = {}
        with safe_open(path, framework="pt", device="cpu") as handle:
            for key in handle.keys():
                out[key] = handle.get_tensor(key)
        return _coerce_mapping(out)
    raise ValueError("Unsupported input format. Use .json, .npz, .npy, .pt, .pth, or .safetensors")


def _as_list(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _flatten_matrix(data: Any, rows: int, cols: int, name: str) -> List[float]:
    data = _as_list(data)
    if isinstance(data, list) and data and isinstance(data[0], list):
        if len(data) != rows:
            raise ValueError(f"{name} row count mismatch: {len(data)} != {rows}")
        flat: List[float] = []
        for r in data:
            if not isinstance(r, list) or len(r) != cols:
                raise ValueError(f"{name} column count mismatch")
            for v in r:
                flat.append(float(v))
        return flat
    if isinstance(data, list):
        if len(data) != rows * cols:
            raise ValueError(f"{name} length mismatch: {len(data)} != {rows * cols}")
        return [float(v) for v in data]
    raise ValueError(f"{name} must be a list or 2D list")


def _flatten_conv1d(data: Any, out_ch: int, in_ch: int, kernel: int, name: str) -> List[float]:
    data = _as_list(data)
    if isinstance(data, list) and data and not isinstance(data[0], list):
        if len(data) != out_ch * in_ch * kernel:
            raise ValueError(f"{name} length mismatch: {len(data)} != {out_ch * in_ch * kernel}")
        return [float(v) for v in data]
    if not isinstance(data, list) or len(data) != out_ch:
        raise ValueError(f"{name} outer dimension mismatch")
    flat: List[float] = []
    for oc in data:
        oc = _as_list(oc)
        if isinstance(oc, list) and oc and isinstance(oc[0], list):
            if len(oc) != in_ch:
                raise ValueError(f"{name} in_channel count mismatch")
            for chan in oc:
                if not isinstance(chan, list) or len(chan) != kernel:
                    raise ValueError(f"{name} kernel length mismatch")
                for v in chan:
                    flat.append(float(v))
        elif isinstance(oc, list):
            if len(oc) != in_ch * kernel:
                raise ValueError(f"{name} flattened length mismatch")
            for v in oc:
                flat.append(float(v))
        else:
            raise ValueError(f"{name} must be a nested list")
    return flat


def _flatten_conv2d(data: Any, out_ch: int, kernel: int, name: str) -> List[float]:
    data = _as_list(data)
    if isinstance(data, list) and data and not isinstance(data[0], list):
        if len(data) != out_ch * kernel * kernel:
            raise ValueError(f"{name} length mismatch: {len(data)} != {out_ch * kernel * kernel}")
        return [float(v) for v in data]
    if not isinstance(data, list) or len(data) != out_ch:
        raise ValueError(f"{name} outer dimension mismatch")
    flat: List[float] = []
    for oc in data:
        oc = _as_list(oc)
        # Accept torch Conv2d single-channel shape [1][kernel][kernel] by
        # unwrapping the channel axis.
        if (
            isinstance(oc, list)
            and len(oc) == 1
            and isinstance(oc[0], list)
            and oc[0]
            and isinstance(oc[0][0], list)
        ):
            oc = oc[0]
        if isinstance(oc, list) and oc and isinstance(oc[0], list):
            if len(oc) != kernel:
                raise ValueError(f"{name} kernel rows mismatch")
            for row in oc:
                if not isinstance(row, list) or len(row) != kernel:
                    raise ValueError(f"{name} kernel cols mismatch")
                for v in row:
                    flat.append(float(v))
        elif isinstance(oc, list):
            if len(oc) != kernel * kernel:
                raise ValueError(f"{name} flattened length mismatch")
            for v in oc:
                flat.append(float(v))
        else:
            raise ValueError(f"{name} must be a nested list")
    return flat


def _matrix_shape(data: Any) -> Tuple[int, int] | None:
    data = _as_list(data)
    if isinstance(data, list) and data and isinstance(data[0], list):
        rows = len(data)
        cols = len(data[0]) if rows > 0 else 0
        for row in data:
            if not isinstance(row, list) or len(row) != cols:
                return None
        return rows, cols
    return None


def _vector(data: Any, length: int, name: str) -> List[float]:
    data = _as_list(data)
    if isinstance(data, list):
        if len(data) != length:
            raise ValueError(f"{name} length mismatch: {len(data)} != {length}")
        return [float(v) for v in data]
    if length == 1:
        return [float(data)]
    raise ValueError(f"{name} must be a list")


def _quantize_i8(values: List[float], scale_q16: int | None) -> Tuple[List[int], int]:
    if not values:
        return [], Q16

    if scale_q16 is None:
        max_abs = max(abs(v) for v in values)
        if max_abs == 0:
            scale_q16 = Q16
        else:
            scale_real = max_abs / 127.0
            scale_q16 = max(1, int(round(scale_real * Q16)))

    scale_real = scale_q16 / Q16
    if scale_real == 0:
        scale_real = 1.0

    q: List[int] = []
    for v in values:
        qi = int(round(v / scale_real))
        if qi > 127:
            qi = 127
        elif qi < -128:
            qi = -128
        q.append(qi)
    return q, scale_q16


def _to_i32_q16(values: List[float]) -> List[int]:
    out: List[int] = []
    for v in values:
        out.append(int(round(v * Q16)))
    return out


def convert_linear(
    input_data: Dict[str, Any],
    input_dim: int,
    output_dim: int,
    output_path: Path,
    scale_q16: int | None,
    bias: bool,
) -> LinearResult:
    if "w" not in input_data:
        raise ValueError("Missing 'w' in input data")
    w_data = _as_list(input_data["w"])
    if output_dim == 1:
        if isinstance(w_data, list) and w_data and isinstance(w_data[0], list):
            if len(w_data) != 1:
                raise ValueError(f"w row count mismatch: {len(w_data)} != 1")
            w = _vector(w_data[0], input_dim, "w")
        else:
            w = _vector(w_data, input_dim, "w")
    else:
        w = _flatten_matrix(w_data, output_dim, input_dim, "w")

    w_q, scale_q16 = _quantize_i8(w, scale_q16)
    b_q16: List[int] = []
    if bias:
        if "b" in input_data:
            b_vals = _vector(input_data["b"], output_dim, "b")
        else:
            b_vals = [0.0] * output_dim
        b_q16 = _to_i32_q16(b_vals)

    buf = bytearray()
    for q in w_q:
        buf.append(q & 0xFF)
    for b in b_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return LinearResult(scale_q16=scale_q16)


def convert_mlp(
    input_data: Dict[str, Any],
    input_dim: int,
    hidden_dim: int,
    output_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
) -> MlpResult:
    for key in ("w1", "w2"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_matrix(input_data["w1"], hidden_dim, input_dim, "w1")
    w2 = _flatten_matrix(input_data["w2"], output_dim, hidden_dim, "w2")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)

    if "b1" in input_data:
        b1_vals = _vector(input_data["b1"], hidden_dim, "b1")
    else:
        b1_vals = [0.0] * hidden_dim
    if "b2" in input_data:
        b2_vals = _vector(input_data["b2"], output_dim, "b2")
    else:
        b2_vals = [0.0] * output_dim

    b1_q16 = _to_i32_q16(b1_vals)
    b2_q16 = _to_i32_q16(b2_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return MlpResult(w1_scale_q16=w1_scale_q16, w2_scale_q16=w2_scale_q16)


def convert_mlp2(
    input_data: Dict[str, Any],
    input_dim: int,
    hidden_dim1: int,
    hidden_dim2: int,
    output_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    w3_scale_q16: int | None,
    bias: bool,
) -> Mlp2Result:
    for key in ("w1", "w2", "w3"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_matrix(input_data["w1"], hidden_dim1, input_dim, "w1")
    w2 = _flatten_matrix(input_data["w2"], hidden_dim2, hidden_dim1, "w2")
    w3 = _flatten_matrix(input_data["w3"], output_dim, hidden_dim2, "w3")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)
    w3_q, w3_scale_q16 = _quantize_i8(w3, w3_scale_q16)

    b1_q16: List[int] = []
    b2_q16: List[int] = []
    b3_q16: List[int] = []
    if bias:
        if "b1" in input_data:
            b1_vals = _vector(input_data["b1"], hidden_dim1, "b1")
        else:
            b1_vals = [0.0] * hidden_dim1
        if "b2" in input_data:
            b2_vals = _vector(input_data["b2"], hidden_dim2, "b2")
        else:
            b2_vals = [0.0] * hidden_dim2
        if "b3" in input_data:
            b3_vals = _vector(input_data["b3"], output_dim, "b3")
        else:
            b3_vals = [0.0] * output_dim
        b1_q16 = _to_i32_q16(b1_vals)
        b2_q16 = _to_i32_q16(b2_vals)
        b3_q16 = _to_i32_q16(b3_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))
    for q in w3_q:
        buf.append(q & 0xFF)
    for b in b3_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return Mlp2Result(
        w1_scale_q16=w1_scale_q16,
        w2_scale_q16=w2_scale_q16,
        w3_scale_q16=w3_scale_q16,
    )


def convert_mlp3(
    input_data: Dict[str, Any],
    input_dim: int,
    hidden_dim1: int,
    hidden_dim2: int,
    hidden_dim3: int,
    output_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    w3_scale_q16: int | None,
    w4_scale_q16: int | None,
    bias: bool,
) -> Mlp3Result:
    for key in ("w1", "w2", "w3", "w4"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_matrix(input_data["w1"], hidden_dim1, input_dim, "w1")
    w2 = _flatten_matrix(input_data["w2"], hidden_dim2, hidden_dim1, "w2")
    w3 = _flatten_matrix(input_data["w3"], hidden_dim3, hidden_dim2, "w3")
    w4 = _flatten_matrix(input_data["w4"], output_dim, hidden_dim3, "w4")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)
    w3_q, w3_scale_q16 = _quantize_i8(w3, w3_scale_q16)
    w4_q, w4_scale_q16 = _quantize_i8(w4, w4_scale_q16)

    b1_q16: List[int] = []
    b2_q16: List[int] = []
    b3_q16: List[int] = []
    b4_q16: List[int] = []
    if bias:
        if "b1" in input_data:
            b1_vals = _vector(input_data["b1"], hidden_dim1, "b1")
        else:
            b1_vals = [0.0] * hidden_dim1
        if "b2" in input_data:
            b2_vals = _vector(input_data["b2"], hidden_dim2, "b2")
        else:
            b2_vals = [0.0] * hidden_dim2
        if "b3" in input_data:
            b3_vals = _vector(input_data["b3"], hidden_dim3, "b3")
        else:
            b3_vals = [0.0] * hidden_dim3
        if "b4" in input_data:
            b4_vals = _vector(input_data["b4"], output_dim, "b4")
        else:
            b4_vals = [0.0] * output_dim
        b1_q16 = _to_i32_q16(b1_vals)
        b2_q16 = _to_i32_q16(b2_vals)
        b3_q16 = _to_i32_q16(b3_vals)
        b4_q16 = _to_i32_q16(b4_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))
    for q in w3_q:
        buf.append(q & 0xFF)
    for b in b3_q16:
        buf.extend(struct.pack("<i", b))
    for q in w4_q:
        buf.append(q & 0xFF)
    for b in b4_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return Mlp3Result(
        w1_scale_q16=w1_scale_q16,
        w2_scale_q16=w2_scale_q16,
        w3_scale_q16=w3_scale_q16,
        w4_scale_q16=w4_scale_q16,
    )


def convert_cnn1d(
    input_data: Dict[str, Any],
    input_channels: int,
    kernel_size: int,
    out_channels: int,
    output_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    bias: bool,
) -> CnnResult:
    for key in ("w1", "w2"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_conv1d(input_data["w1"], out_channels, input_channels, kernel_size, "w1")
    w2 = _flatten_matrix(input_data["w2"], output_dim, out_channels, "w2")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)

    b1_q16: List[int] = []
    b2_q16: List[int] = []
    if bias:
        if "b1" in input_data:
            b1_vals = _vector(input_data["b1"], out_channels, "b1")
        else:
            b1_vals = [0.0] * out_channels
        if "b2" in input_data:
            b2_vals = _vector(input_data["b2"], output_dim, "b2")
        else:
            b2_vals = [0.0] * output_dim
        b1_q16 = _to_i32_q16(b1_vals)
        b2_q16 = _to_i32_q16(b2_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return CnnResult(w1_scale_q16=w1_scale_q16, w2_scale_q16=w2_scale_q16)


def convert_tiny_cnn(
    input_data: Dict[str, Any],
    kernel_size: int,
    out_channels: int,
    output_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    bias: bool,
) -> CnnResult:
    for key in ("w1", "w2"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_conv2d(input_data["w1"], out_channels, kernel_size, "w1")
    w2 = _flatten_matrix(input_data["w2"], output_dim, out_channels, "w2")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)

    b1_q16: List[int] = []
    b2_q16: List[int] = []
    if bias:
        if "b1" in input_data:
            b1_vals = _vector(input_data["b1"], out_channels, "b1")
        else:
            b1_vals = [0.0] * out_channels
        if "b2" in input_data:
            b2_vals = _vector(input_data["b2"], output_dim, "b2")
        else:
            b2_vals = [0.0] * output_dim
        b1_q16 = _to_i32_q16(b1_vals)
        b2_q16 = _to_i32_q16(b2_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return CnnResult(w1_scale_q16=w1_scale_q16, w2_scale_q16=w2_scale_q16)


def convert_two_tower(
    input_data: Dict[str, Any],
    input_dim_a: int,
    input_dim_b: int,
    embed_dim: int,
    output_path: Path,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    bias: bool,
) -> TwoTowerResult:
    for key in ("w1", "w2"):
        if key not in input_data:
            raise ValueError(f"Missing '{key}' in input data")

    w1 = _flatten_matrix(input_data["w1"], embed_dim, input_dim_a, "w1")
    w2 = _flatten_matrix(input_data["w2"], embed_dim, input_dim_b, "w2")

    w1_q, w1_scale_q16 = _quantize_i8(w1, w1_scale_q16)
    w2_q, w2_scale_q16 = _quantize_i8(w2, w2_scale_q16)

    b1_q16: List[int] = []
    b2_q16: List[int] = []
    if bias:
        if "b1" in input_data:
            b1_vals = _vector(input_data["b1"], embed_dim, "b1")
        else:
            b1_vals = [0.0] * embed_dim
        if "b2" in input_data:
            b2_vals = _vector(input_data["b2"], embed_dim, "b2")
        else:
            b2_vals = [0.0] * embed_dim
        b1_q16 = _to_i32_q16(b1_vals)
        b2_q16 = _to_i32_q16(b2_vals)

    buf = bytearray()
    for q in w1_q:
        buf.append(q & 0xFF)
    for b in b1_q16:
        buf.extend(struct.pack("<i", b))
    for q in w2_q:
        buf.append(q & 0xFF)
    for b in b2_q16:
        buf.extend(struct.pack("<i", b))

    output_path.write_bytes(buf)
    return TwoTowerResult(w1_scale_q16=w1_scale_q16, w2_scale_q16=w2_scale_q16)


def convert_tree(
    input_data: Dict[str, Any],
    tree_count: int,
    node_count: int,
    tree_stride: int | None,
    output_path: Path,
) -> None:
    trees = input_data.get("trees")
    if trees is None:
        nodes = input_data.get("nodes")
        if nodes is None:
            raise ValueError("tree input requires 'nodes' or 'trees'")
        trees = [nodes]
    if not isinstance(trees, list) or not trees:
        raise ValueError("trees must be a non-empty list")
    if tree_count != len(trees):
        raise ValueError("tree_count does not match number of trees in input")

    node_bytes = node_count * 20
    if tree_stride is None:
        tree_stride = node_bytes
    if not isinstance(tree_stride, int) or tree_stride <= 0:
        raise ValueError("tree_stride must be a positive integer when provided")
    if tree_stride < node_bytes:
        raise ValueError("tree_stride must be >= node_count * 20")
    if tree_stride % 4 != 0:
        raise ValueError("tree_stride must be 4-byte aligned")

    buf = bytearray()
    for tree in trees:
        if not isinstance(tree, list):
            raise ValueError("each tree must be a list of nodes")
        if len(tree) != node_count:
            raise ValueError("tree node count mismatch")
        for node in tree:
            if not isinstance(node, dict):
                raise ValueError("node must be an object")
            feature = int(node.get("feature", -1))
            threshold = node.get("threshold", 0.0)
            left = int(node.get("left", -1))
            right = int(node.get("right", -1))
            value = node.get("value", 0.0)
            threshold_q16 = int(round(float(threshold) * Q16))
            value_q16 = int(round(float(value) * Q16))
            buf.extend(struct.pack("<iiiii", feature, threshold_q16, left, right, value_q16))
        padding = tree_stride - node_bytes
        if padding:
            buf.extend(b"\x00" * padding)

    output_path.write_bytes(buf)


def infer_template(layout: str | None) -> str | None:
    if not layout:
        return None
    layout = layout.lower()
    if "cnn1d" in layout or "conv1d" in layout:
        return "cnn1d"
    if "tiny_cnn" in layout or "cnn2d" in layout or "tinycnn" in layout:
        return "tiny_cnn"
    if "mlp3" in layout:
        return "mlp3"
    if "mlp2" in layout:
        return "mlp2"
    if "softmax" in layout or "logreg" in layout or "logistic" in layout:
        return "softmax"
    if "naive" in layout or "bayes" in layout:
        return "naive_bayes"
    if "two_tower" in layout or "twotower" in layout or "two-tower" in layout:
        return "two_tower"
    if "tree" in layout or "gbdt" in layout:
        return "tree"
    if "linear" in layout:
        return "linear"
    if "mlp" in layout:
        return "mlp"
    return None


def update_manifest_scales(manifest_path: Path, scales: Dict[str, int]) -> None:
    text = manifest_path.read_text()
    lines = text.splitlines()
    out: List[str] = []
    in_scales = False
    updated = set()
    indent = ""
    seen_scales = False

    def flush_missing() -> None:
        nonlocal out, updated
        for key, val in scales.items():
            if key in updated:
                continue
            out.append(f"{indent}{key} = {val}")
            updated.add(key)

    for line in lines:
        if re.match(r"^\s*\[weights\.scales\]\s*$", line):
            in_scales = True
            seen_scales = True
            out.append(line)
            continue

        if in_scales and re.match(r"^\s*\[", line):
            flush_missing()
            in_scales = False
            out.append(line)
            continue

        if in_scales:
            key_match = re.match(r"^(\s*)([A-Za-z0-9_]+)\s*=", line)
            if key_match:
                indent = key_match.group(1)
                key = key_match.group(2)
                if key in scales:
                    out.append(f"{indent}{key} = {scales[key]}")
                    updated.add(key)
                    continue
        out.append(line)

    if in_scales:
        flush_missing()
    elif scales and not seen_scales:
        if out and out[-1].strip() != "":
            out.append("")
        out.append("[weights.scales]")
        for key, val in scales.items():
            out.append(f"{key} = {val}")

    trailing = "\n" if text.endswith("\n") else ""
    manifest_path.write_text("\n".join(out) + trailing)


def load_and_convert(
    manifest_path: Path,
    input_path: Path,
    template: str | None,
    output_path: Path | None,
    scale_q16: int | None,
    w1_scale_q16: int | None,
    w2_scale_q16: int | None,
    w3_scale_q16: int | None,
    w4_scale_q16: int | None,
    update_manifest: bool,
    input_dim_override: int | None,
    output_dim_override: int | None,
    hidden_dim_override: int | None,
    hidden_dim1_override: int | None,
    hidden_dim2_override: int | None,
    hidden_dim3_override: int | None,
    bias: bool,
    keymap: Dict[str, str] | None,
    input_dim_a_override: int | None,
    input_dim_b_override: int | None,
    embed_dim_override: int | None,
    tree_count_override: int | None,
    tree_node_count_override: int | None,
) -> None:
    manifest = json.loads(manifest_path.read_text()) if False else None
    # load manifest as dict
    from .manifest import load_manifest

    manifest = load_manifest(manifest_path)
    weights = manifest.get("weights", {}) if isinstance(manifest, dict) else {}
    layout = weights.get("layout") if isinstance(weights, dict) else None

    resolved_template = template or infer_template(layout)
    if resolved_template is None:
        raise ValueError("Unable to infer template; pass --template")

    schema = manifest.get("schema", {}) if isinstance(manifest, dict) else {}
    schema_type = schema.get("type") if isinstance(schema, dict) else None

    input_dim = input_dim_override
    output_dim = output_dim_override

    if input_dim is None or output_dim is None:
        if schema_type == "vector":
            vector = schema.get("vector", {}) if isinstance(schema, dict) else {}
            input_shape = vector.get("input_shape")
            output_shape = vector.get("output_shape")
            if not isinstance(input_shape, list) or not isinstance(output_shape, list):
                raise ValueError("schema.vector input_shape/output_shape required")
            if input_dim is None:
                input_dim = math.prod(input_shape)
            if output_dim is None:
                output_dim = math.prod(output_shape)
        elif schema_type == "time_series":
            ts = schema.get("time_series", {}) if isinstance(schema, dict) else {}
            window = ts.get("window")
            features = ts.get("features")
            output_shape = ts.get("output_shape")
            if not isinstance(window, int) or not isinstance(features, int):
                raise ValueError("schema.time_series window/features required")
            if input_dim is None:
                input_dim = window * features
            if output_dim is None:
                if not isinstance(output_shape, list):
                    raise ValueError("schema.time_series output_shape required")
                output_dim = math.prod(output_shape)
        elif schema_type == "graph":
            gr = schema.get("graph", {}) if isinstance(schema, dict) else {}
            node_dim = gr.get("node_feature_dim")
            output_shape = gr.get("output_shape")
            if input_dim is None:
                if not isinstance(node_dim, int):
                    raise ValueError("schema.graph node_feature_dim required")
                input_dim = node_dim
            if output_dim is None:
                if not isinstance(output_shape, list):
                    raise ValueError("schema.graph output_shape required")
                output_dim = math.prod(output_shape)
        elif schema_type == "custom":
            if input_dim is None or output_dim is None:
                raise ValueError("custom schema requires --input-dim and --output-dim")
        else:
            raise ValueError("schema.type must be vector, time_series, graph, or custom")

    if input_dim is None or output_dim is None:
        raise ValueError("input/output dimensions could not be resolved")

    if output_path is None:
        blobs = weights.get("blobs") if isinstance(weights, dict) else None
        if isinstance(blobs, list) and blobs:
            blob = blobs[0]
            if isinstance(blob, dict) and isinstance(blob.get("file"), str):
                output_path = manifest_path.parent / blob["file"]
    if output_path is None:
        output_path = manifest_path.parent / "weights.bin"

    input_data = _load_input(input_path)
    if keymap:
        for dest, src in keymap.items():
            if src not in input_data:
                raise ValueError(f"Key '{src}' not found in input for mapping to '{dest}'")
            input_data[dest] = input_data[src]

    if resolved_template == "linear":
        result = convert_linear(
            input_data,
            input_dim=input_dim,
            output_dim=output_dim,
            output_path=output_path,
            scale_q16=scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(manifest_path, {"w_scale_q16": result.scale_q16})
    elif resolved_template in ("softmax", "naive_bayes"):
        result = convert_linear(
            input_data,
            input_dim=input_dim,
            output_dim=output_dim,
            output_path=output_path,
            scale_q16=scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(manifest_path, {"w_scale_q16": result.scale_q16})
    elif resolved_template == "mlp":
        hidden_dim = hidden_dim_override
        if hidden_dim is None and "hidden_dim" in input_data:
            hidden_dim = int(input_data["hidden_dim"])
        if hidden_dim is None:
            w1 = _as_list(input_data.get("w1"))
            if isinstance(w1, list) and w1 and isinstance(w1[0], list):
                hidden_dim = len(w1)
        if hidden_dim is None:
            raise ValueError("hidden_dim not found; include in input or pass 2D w1")
        result = convert_mlp(
            input_data,
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            output_dim=output_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                },
            )
    elif resolved_template == "mlp2":
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        hidden_dim1 = hidden_dim1_override or build.get("hidden_dim1")
        hidden_dim2 = hidden_dim2_override or build.get("hidden_dim2")
        if hidden_dim1 is None:
            shape = _matrix_shape(input_data.get("w1"))
            if shape:
                hidden_dim1 = shape[0]
        if hidden_dim2 is None:
            shape = _matrix_shape(input_data.get("w2"))
            if shape:
                hidden_dim2 = shape[0]
        if hidden_dim1 is None or hidden_dim2 is None:
            raise ValueError("hidden_dim1 and hidden_dim2 required for mlp2")
        result = convert_mlp2(
            input_data,
            input_dim=input_dim,
            hidden_dim1=int(hidden_dim1),
            hidden_dim2=int(hidden_dim2),
            output_dim=output_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            w3_scale_q16=w3_scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                    "w3_scale_q16": result.w3_scale_q16,
                },
            )
    elif resolved_template == "mlp3":
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        hidden_dim1 = hidden_dim1_override or build.get("hidden_dim1")
        hidden_dim2 = hidden_dim2_override or build.get("hidden_dim2")
        hidden_dim3 = hidden_dim3_override or build.get("hidden_dim3")
        if hidden_dim1 is None:
            shape = _matrix_shape(input_data.get("w1"))
            if shape:
                hidden_dim1 = shape[0]
        if hidden_dim2 is None:
            shape = _matrix_shape(input_data.get("w2"))
            if shape:
                hidden_dim2 = shape[0]
        if hidden_dim3 is None:
            shape = _matrix_shape(input_data.get("w3"))
            if shape:
                hidden_dim3 = shape[0]
        if hidden_dim1 is None or hidden_dim2 is None or hidden_dim3 is None:
            raise ValueError("hidden_dim1/2/3 required for mlp3")
        result = convert_mlp3(
            input_data,
            input_dim=input_dim,
            hidden_dim1=int(hidden_dim1),
            hidden_dim2=int(hidden_dim2),
            hidden_dim3=int(hidden_dim3),
            output_dim=output_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            w3_scale_q16=w3_scale_q16,
            w4_scale_q16=w4_scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                    "w3_scale_q16": result.w3_scale_q16,
                    "w4_scale_q16": result.w4_scale_q16,
                },
            )
    elif resolved_template == "two_tower":
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        input_dim_a = input_dim_a_override or build.get("tower_input_a")
        input_dim_b = input_dim_b_override or build.get("tower_input_b")
        embed_dim = embed_dim_override or build.get("embed_dim")
        if not isinstance(input_dim_a, int) or not isinstance(input_dim_b, int):
            raise ValueError("build.tower_input_a and build.tower_input_b required for two_tower")
        if not isinstance(embed_dim, int):
            raise ValueError("build.embed_dim required for two_tower")
        if input_dim_a + input_dim_b != input_dim:
            raise ValueError("tower_input_a + tower_input_b must equal schema input_dim")
        result = convert_two_tower(
            input_data,
            input_dim_a=input_dim_a,
            input_dim_b=input_dim_b,
            embed_dim=embed_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                },
            )
    elif resolved_template == "tree":
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        tree_count = tree_count_override or build.get("tree_count", 1)
        node_count = tree_node_count_override or build.get("tree_node_count")
        tree_stride = build.get("tree_stride")
        if not isinstance(tree_count, int) or tree_count < 1:
            raise ValueError("build.tree_count must be >= 1 for tree template")
        if not isinstance(node_count, int) or node_count < 1:
            raise ValueError("build.tree_node_count required for tree template")
        convert_tree(
            input_data,
            tree_count=int(tree_count),
            node_count=int(node_count),
            tree_stride=int(tree_stride) if tree_stride is not None else None,
            output_path=output_path,
        )
    elif resolved_template == "cnn1d":
        if schema_type != "time_series":
            raise ValueError("cnn1d template requires schema.type = time_series")
        ts = schema.get("time_series", {}) if isinstance(schema, dict) else {}
        window = ts.get("window")
        features = ts.get("features")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required for cnn1d")
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        kernel_size = build.get("kernel_size")
        out_channels = build.get("out_channels")
        stride = build.get("stride", 1)
        if not isinstance(kernel_size, int) or kernel_size < 1:
            raise ValueError("build.kernel_size required for cnn1d")
        if not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("build.out_channels required for cnn1d")
        if not isinstance(stride, int) or stride < 1:
            raise ValueError("build.stride must be >= 1 for cnn1d")
        result = convert_cnn1d(
            input_data,
            input_channels=features,
            kernel_size=kernel_size,
            out_channels=out_channels,
            output_dim=output_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                },
            )
    elif resolved_template == "tiny_cnn":
        if schema_type != "vector":
            raise ValueError("tiny_cnn template requires schema.type = vector")
        vec = schema.get("vector", {}) if isinstance(schema, dict) else {}
        input_shape = vec.get("input_shape")
        build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
        input_height = build.get("input_height")
        input_width = build.get("input_width")
        if (input_height is None or input_width is None) and isinstance(input_shape, list) and len(input_shape) == 2:
            input_height, input_width = input_shape
        if not isinstance(input_height, int) or not isinstance(input_width, int):
            raise ValueError("build.input_height/input_width required for tiny_cnn")
        kernel_size = build.get("kernel_size")
        out_channels = build.get("out_channels")
        stride = build.get("stride", 1)
        if not isinstance(kernel_size, int) or kernel_size < 1:
            raise ValueError("build.kernel_size required for tiny_cnn")
        if not isinstance(out_channels, int) or out_channels < 1:
            raise ValueError("build.out_channels required for tiny_cnn")
        if not isinstance(stride, int) or stride < 1:
            raise ValueError("build.stride must be >= 1 for tiny_cnn")
        if input_height * input_width != input_dim:
            raise ValueError("tiny_cnn input_height * input_width must equal schema input_dim")
        result = convert_tiny_cnn(
            input_data,
            kernel_size=kernel_size,
            out_channels=out_channels,
            output_dim=output_dim,
            output_path=output_path,
            w1_scale_q16=w1_scale_q16,
            w2_scale_q16=w2_scale_q16,
            bias=bias,
        )
        if update_manifest:
            update_manifest_scales(
                manifest_path,
                {
                    "w1_scale_q16": result.w1_scale_q16,
                    "w2_scale_q16": result.w2_scale_q16,
                },
            )
    else:
        raise ValueError(f"Unsupported template: {resolved_template}")
