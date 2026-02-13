"""Training harness with quantization + calibration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


def _require_numpy() -> Any:
    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise ImportError("numpy is required for training (pip install numpy)") from exc
    return np


def _require_torch() -> Any:
    try:
        import torch  # type: ignore
    except ImportError as exc:
        raise ImportError("torch is required for training (pip install torch)") from exc
    return torch


def _require_sklearn() -> Any:
    try:
        import sklearn  # type: ignore
    except ImportError as exc:
        raise ImportError("scikit-learn is required for this template (pip install scikit-learn)") from exc
    return sklearn


def _load_manifest(path: Path) -> Dict[str, Any]:
    from ..manifest import load_manifest

    return load_manifest(path)


def _schema_dims(manifest: Dict[str, Any]) -> Tuple[int, int]:
    from ..util import product

    schema = manifest.get("schema", {})
    schema_type = schema.get("type")
    if schema_type == "vector":
        vec = schema.get("vector", {})
        input_shape = vec.get("input_shape")
        output_shape = vec.get("output_shape")
        if not isinstance(input_shape, list) or not isinstance(output_shape, list):
            raise ValueError("schema.vector input_shape/output_shape required")
        return product(input_shape), product(output_shape)
    if schema_type == "time_series":
        ts = schema.get("time_series", {})
        window = ts.get("window")
        features = ts.get("features")
        output_shape = ts.get("output_shape")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required")
        if not isinstance(output_shape, list):
            raise ValueError("schema.time_series output_shape required")
        return window * features, product(output_shape)
    raise ValueError("Training harness supports vector/time_series schemas only")


def _infer_template(manifest: Dict[str, Any], template: str | None) -> str:
    if template:
        return template
    weights = manifest.get("weights", {})
    layout = weights.get("layout") if isinstance(weights, dict) else None
    from ..convert import infer_template

    inferred = infer_template(layout)
    if inferred is None:
        raise ValueError("Unable to infer template; pass --template")
    return inferred


def _load_csv(path: Path, label_col: str | None) -> Tuple[Any, Any]:
    np = _require_numpy()
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        pd = None

    if pd is None:
        data = np.genfromtxt(path, delimiter=",", dtype=np.float32)
        if data.ndim != 2 or data.shape[1] < 2:
            raise ValueError("CSV must have at least 2 columns")
        label_idx = -1 if label_col is None else int(label_col)
        x = np.delete(data, label_idx, axis=1)
        y = data[:, label_idx]
        return x, y

    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("CSV is empty")
    if label_col is None:
        label_col = df.columns[-1]
    try:
        label_series = df[label_col]
        features = df.drop(columns=[label_col])
    except KeyError as exc:
        raise ValueError(f"label column not found: {label_col}") from exc
    return features.to_numpy(dtype="float32"), label_series.to_numpy()


def _load_npz(path: Path, template: str) -> Dict[str, Any]:
    np = _require_numpy()
    data = np.load(path)
    payload: Dict[str, Any] = {}

    if template == "two_tower":
        if "x_a" not in data or "x_b" not in data:
            raise ValueError("npz for two_tower must include x_a and x_b")
        payload["x_a"] = data["x_a"]
        payload["x_b"] = data["x_b"]
        payload["y"] = data["y"] if "y" in data else None
    else:
        if "x" not in data:
            raise ValueError("npz must include x array")
        payload["x"] = data["x"]
        payload["y"] = data["y"] if "y" in data else None
    return payload


def _load_dataset(path: Path, template: str, label_col: str | None) -> Dict[str, Any]:
    if path.suffix.lower() == ".npz":
        return _load_npz(path, template)
    if path.suffix.lower() == ".csv":
        x, y = _load_csv(path, label_col)
        return {"x": x, "y": y}
    raise ValueError("Unsupported dataset format (use .csv or .npz)")


def _split_indices(n: int, val_split: float, seed: int) -> Tuple[Any, Any]:
    np = _require_numpy()
    idx = np.arange(n)
    rng = np.random.default_rng(seed)
    rng.shuffle(idx)
    val_size = int(round(n * val_split))
    val_idx = idx[:val_size]
    train_idx = idx[val_size:]
    return train_idx, val_idx


def _train_val_split(x: Any, y: Any, val_split: float, seed: int) -> Tuple[Any, Any, Any, Any]:
    if y is None:
        raise ValueError("dataset must include labels (y)")
    train_idx, val_idx = _split_indices(len(x), val_split, seed)
    return x[train_idx], y[train_idx], x[val_idx], y[val_idx]
    return x[train_idx], y[train_idx], x[val_idx], y[val_idx]


def _compute_scale_q16(values: Any, percentile: float | None) -> int:
    np = _require_numpy()
    flat = np.abs(np.asarray(values).reshape(-1))
    if flat.size == 0:
        return 1 << 16
    if percentile is not None:
        max_abs = float(np.percentile(flat, percentile))
    else:
        max_abs = float(flat.max())
    if max_abs == 0:
        return 1 << 16
    scale_real = max_abs / 127.0
    return max(1, int(round(scale_real * (1 << 16))))


def _write_calibration(path: Path, values: Any, percentile: float) -> None:
    np = _require_numpy()
    flat = np.abs(np.asarray(values).reshape(-1))
    if flat.size == 0:
        clip = 0.0
    else:
        clip = float(np.percentile(flat, percentile))
    payload = {
        "percentile": percentile,
        "clip_abs": clip,
        "q16_scale": 1 << 16,
    }
    path.write_text(json.dumps(payload, indent=2))


def _as_torch(x: Any, torch: Any) -> Any:
    return torch.tensor(x, dtype=torch.float32)


def _train_loop(model: Any, loader: Any, loss_fn: Any, optimizer: Any, device: str, epochs: int) -> None:
    torch = _require_torch()
    model.train()
    for _ in range(epochs):
        for batch in loader:
            optimizer.zero_grad(set_to_none=True)
            if isinstance(batch, (list, tuple)) and len(batch) == 3:
                xa, xb, y = batch
                pred = model(xa.to(device), xb.to(device))
                loss = loss_fn(pred, y.to(device))
            else:
                x, y = batch
                pred = model(x.to(device))
                loss = loss_fn(pred, y.to(device))
            loss.backward()
            optimizer.step()


def _prepare_labels(y: Any, task: str, output_dim: int, torch: Any) -> Any:
    if task == "classification":
        if output_dim == 1:
            return torch.tensor(y, dtype=torch.float32).view(-1, 1)
        return torch.tensor(y, dtype=torch.long)
    return torch.tensor(y, dtype=torch.float32).view(-1, output_dim)


def _loss_fn(task: str, output_dim: int, torch: Any) -> Any:
    if task == "classification":
        if output_dim == 1:
            return torch.nn.BCEWithLogitsLoss()
        return torch.nn.CrossEntropyLoss()
    return torch.nn.MSELoss()


def _linear_model(input_dim: int, output_dim: int, torch: Any, has_bias: bool) -> Any:
    return torch.nn.Linear(input_dim, output_dim, bias=has_bias)


def _mlp_model(input_dim: int, hidden_dims: list[int], output_dim: int, torch: Any, has_bias: bool) -> Any:
    layers = []
    prev = input_dim
    for h in hidden_dims:
        layers.append(torch.nn.Linear(prev, h, bias=has_bias))
        layers.append(torch.nn.ReLU())
        prev = h
    layers.append(torch.nn.Linear(prev, output_dim, bias=has_bias))
    return torch.nn.Sequential(*layers)


def _cnn1d_model(features: int, kernel_size: int, stride: int, out_channels: int, output_dim: int, torch: Any, has_bias: bool) -> Any:
    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv = torch.nn.Conv1d(features, out_channels, kernel_size, stride=stride, bias=has_bias)
            self.fc = torch.nn.Linear(out_channels, output_dim, bias=has_bias)

        def forward(self, x: Any) -> Any:
            # x: (N, L, C)
            x = x.transpose(1, 2)
            y = torch.relu(self.conv(x))
            y = y.mean(dim=2)
            return self.fc(y)

    return Model()


def _tiny_cnn_model(input_height: int, input_width: int, kernel_size: int, stride: int, out_channels: int, output_dim: int, torch: Any, has_bias: bool) -> Any:
    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv = torch.nn.Conv2d(1, out_channels, kernel_size, stride=stride, bias=has_bias)
            self.fc = torch.nn.Linear(out_channels, output_dim, bias=has_bias)

        def forward(self, x: Any) -> Any:
            x = x.view(-1, 1, input_height, input_width)
            y = torch.relu(self.conv(x))
            y = y.mean(dim=(2, 3))
            return self.fc(y)

    return Model()


def _two_tower_model(input_dim_a: int, input_dim_b: int, embed_dim: int, torch: Any, has_bias: bool) -> Any:
    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.tower_a = torch.nn.Linear(input_dim_a, embed_dim, bias=has_bias)
            self.tower_b = torch.nn.Linear(input_dim_b, embed_dim, bias=has_bias)

        def forward(self, xa: Any, xb: Any) -> Any:
            ea = self.tower_a(xa)
            eb = self.tower_b(xb)
            return (ea * eb).sum(dim=1, keepdim=True)

    return Model()


def _extract_weights(model: Any, template: str, has_bias: bool) -> Dict[str, Any]:
    torch = _require_torch()
    state = {k: v.detach().cpu().numpy() for k, v in model.state_dict().items()}

    def bias_or_zeros(key: str, length: int) -> Any:
        if key in state:
            return state[key].tolist()
        return [0.0] * length

    if template in ("linear", "softmax", "naive_bayes"):
        w: Any = state["weight"].tolist()
        if template == "linear" and state["weight"].shape[0] == 1:
            if isinstance(w, list) and w and isinstance(w[0], list):
                w = w[0]
        out = {"w": w}
        if has_bias:
            out["b"] = bias_or_zeros("bias", state["weight"].shape[0])
        return out
    if template == "mlp":
        out = {
            "w1": state["0.weight"].tolist(),
            "w2": state["2.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("0.bias", state["0.weight"].shape[0])
            out["b2"] = bias_or_zeros("2.bias", state["2.weight"].shape[0])
        return out
    if template == "mlp2":
        out = {
            "w1": state["0.weight"].tolist(),
            "w2": state["2.weight"].tolist(),
            "w3": state["4.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("0.bias", state["0.weight"].shape[0])
            out["b2"] = bias_or_zeros("2.bias", state["2.weight"].shape[0])
            out["b3"] = bias_or_zeros("4.bias", state["4.weight"].shape[0])
        return out
    if template == "mlp3":
        out = {
            "w1": state["0.weight"].tolist(),
            "w2": state["2.weight"].tolist(),
            "w3": state["4.weight"].tolist(),
            "w4": state["6.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("0.bias", state["0.weight"].shape[0])
            out["b2"] = bias_or_zeros("2.bias", state["2.weight"].shape[0])
            out["b3"] = bias_or_zeros("4.bias", state["4.weight"].shape[0])
            out["b4"] = bias_or_zeros("6.bias", state["6.weight"].shape[0])
        return out
    if template == "cnn1d":
        out = {
            "w1": state["conv.weight"].tolist(),
            "w2": state["fc.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("conv.bias", state["conv.weight"].shape[0])
            out["b2"] = bias_or_zeros("fc.bias", state["fc.weight"].shape[0])
        return out
    if template == "tiny_cnn":
        out = {
            "w1": state["conv.weight"].tolist(),
            "w2": state["fc.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("conv.bias", state["conv.weight"].shape[0])
            out["b2"] = bias_or_zeros("fc.bias", state["fc.weight"].shape[0])
        return out
    if template == "two_tower":
        out = {
            "w1": state["tower_a.weight"].tolist(),
            "w2": state["tower_b.weight"].tolist(),
        }
        if has_bias:
            out["b1"] = bias_or_zeros("tower_a.bias", state["tower_a.weight"].shape[0])
            out["b2"] = bias_or_zeros("tower_b.bias", state["tower_b.weight"].shape[0])
        return out
    raise ValueError(f"Template not supported for weight extraction: {template}")


def _train_torch(
    template: str,
    manifest: Dict[str, Any],
    data: Dict[str, Any],
    task: str,
    epochs: int,
    batch_size: int,
    lr: float,
    seed: int,
    val_split: float,
    overrides: Dict[str, int | None],
) -> Dict[str, Any]:
    np = _require_numpy()
    torch = _require_torch()
    torch.manual_seed(seed)

    has_bias = not overrides.get("no_bias", False)

    input_dim, output_dim = _schema_dims(manifest)
    build = manifest.get("build", {}) if isinstance(manifest, dict) else {}

    if template == "two_tower":
        xa = np.asarray(data["x_a"], dtype=np.float32)
        xb = np.asarray(data["x_b"], dtype=np.float32)
        y = data.get("y")
        if y is None:
            raise ValueError("two_tower requires labels y")
        y = np.asarray(y, dtype=np.float32).reshape(-1, 1)
        input_dim_a = overrides.get("input_dim_a") or build.get("tower_input_a")
        input_dim_b = overrides.get("input_dim_b") or build.get("tower_input_b")
        embed_dim = overrides.get("embed_dim") or build.get("embed_dim")
        if not isinstance(input_dim_a, int) or not isinstance(input_dim_b, int):
            raise ValueError("build.tower_input_a and build.tower_input_b required")
        if not isinstance(embed_dim, int):
            raise ValueError("build.embed_dim required")
        model = _two_tower_model(input_dim_a, input_dim_b, embed_dim, torch, has_bias)
        train_idx, val_idx = _split_indices(len(xa), val_split, seed)
        xa_train, xa_val = xa[train_idx], xa[val_idx]
        xb_train, xb_val = xb[train_idx], xb[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]
        train_ds = torch.utils.data.TensorDataset(
            _as_torch(xa_train, torch), _as_torch(xb_train, torch), _prepare_labels(y_train, task, 1, torch)
        )
        loader = torch.utils.data.DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        loss_fn = _loss_fn(task, 1, torch)
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        _train_loop(model, loader, loss_fn, optimizer, "cpu", epochs)
        return _extract_weights(model, template, has_bias)

    x = np.asarray(data["x"], dtype=np.float32)
    y = data.get("y")
    if y is None:
        raise ValueError("dataset must include labels y")
    y = np.asarray(y)

    if template == "cnn1d":
        ts = manifest.get("schema", {}).get("time_series", {})
        window = ts.get("window")
        features = ts.get("features")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required")
        if x.ndim == 2:
            if x.shape[1] != input_dim:
                raise ValueError(
                    f"dataset feature count ({x.shape[1]}) does not match schema input_dim ({input_dim})"
                )
        elif x.ndim == 3:
            if x.shape[1] != window or x.shape[2] != features:
                raise ValueError("cnn1d expects input shape (N, window, features)")
        else:
            raise ValueError("cnn1d expects 2D or 3D input array")
    else:
        if x.ndim != 2:
            raise ValueError("dataset features must be a 2D array")
        if x.shape[1] != input_dim:
            raise ValueError(
                f"dataset feature count ({x.shape[1]}) does not match schema input_dim ({input_dim})"
            )

    if task == "classification":
        classes = np.unique(y)
        if output_dim == 1 and classes.size > 2:
            raise ValueError("classification with output_dim=1 only supports binary labels; update schema output_shape")
        if output_dim > 1 and classes.size > output_dim:
            raise ValueError("classification labels exceed schema output_dim")

    if template == "cnn1d":
        ts = manifest.get("schema", {}).get("time_series", {})
        window = ts.get("window")
        features = ts.get("features")
        if not isinstance(window, int) or not isinstance(features, int):
            raise ValueError("schema.time_series window/features required")
        kernel_size = overrides.get("kernel_size") or build.get("kernel_size")
        out_channels = overrides.get("out_channels") or build.get("out_channels")
        stride = overrides.get("stride") or build.get("stride", 1)
        if not isinstance(kernel_size, int) or not isinstance(out_channels, int):
            raise ValueError("build.kernel_size and build.out_channels required")
        if x.ndim == 2:
            x = x.reshape(-1, window, features)
        model = _cnn1d_model(features, kernel_size, int(stride), int(out_channels), output_dim, torch, has_bias)
    elif template == "tiny_cnn":
        vec = manifest.get("schema", {}).get("vector", {})
        input_shape = vec.get("input_shape")
        input_height = overrides.get("input_height") or build.get("input_height")
        input_width = overrides.get("input_width") or build.get("input_width")
        if (input_height is None or input_width is None) and isinstance(input_shape, list) and len(input_shape) == 2:
            input_height, input_width = input_shape
        if not isinstance(input_height, int) or not isinstance(input_width, int):
            raise ValueError("build.input_height/input_width required")
        kernel_size = overrides.get("kernel_size") or build.get("kernel_size")
        out_channels = overrides.get("out_channels") or build.get("out_channels")
        stride = overrides.get("stride") or build.get("stride", 1)
        if not isinstance(kernel_size, int) or not isinstance(out_channels, int):
            raise ValueError("build.kernel_size and build.out_channels required")
        model = _tiny_cnn_model(input_height, input_width, int(kernel_size), int(stride), int(out_channels), output_dim, torch, has_bias)
    elif template == "mlp":
        hidden_dim = overrides.get("hidden_dim") or build.get("hidden_dim")
        if not isinstance(hidden_dim, int):
            raise ValueError("build.hidden_dim required for mlp")
        model = _mlp_model(input_dim, [int(hidden_dim)], output_dim, torch, has_bias)
    elif template == "mlp2":
        h1 = overrides.get("hidden_dim1") or build.get("hidden_dim1")
        h2 = overrides.get("hidden_dim2") or build.get("hidden_dim2")
        if not isinstance(h1, int) or not isinstance(h2, int):
            raise ValueError("build.hidden_dim1/hidden_dim2 required for mlp2")
        model = _mlp_model(input_dim, [int(h1), int(h2)], output_dim, torch, has_bias)
    elif template == "mlp3":
        h1 = overrides.get("hidden_dim1") or build.get("hidden_dim1")
        h2 = overrides.get("hidden_dim2") or build.get("hidden_dim2")
        h3 = overrides.get("hidden_dim3") or build.get("hidden_dim3")
        if not isinstance(h1, int) or not isinstance(h2, int) or not isinstance(h3, int):
            raise ValueError("build.hidden_dim1/hidden_dim2/hidden_dim3 required for mlp3")
        model = _mlp_model(input_dim, [int(h1), int(h2), int(h3)], output_dim, torch, has_bias)
    else:
        model = _linear_model(input_dim, output_dim, torch, has_bias)

    x_train, y_train, _, _ = _train_val_split(x, y, val_split, seed)
    x_train_t = _as_torch(x_train, torch)
    y_train_t = _prepare_labels(y_train, task, output_dim, torch)
    train_ds = torch.utils.data.TensorDataset(x_train_t, y_train_t)
    loader = torch.utils.data.DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    loss_fn = _loss_fn(task, output_dim, torch)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    _train_loop(model, loader, loss_fn, optimizer, "cpu", epochs)
    return _extract_weights(model, template, has_bias)


def _train_naive_bayes(manifest: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    _require_sklearn()
    import numpy as np  # type: ignore
    from sklearn.naive_bayes import MultinomialNB  # type: ignore

    x = np.asarray(data["x"], dtype=np.float32)
    y = np.asarray(data["y"], dtype=np.int64)
    model = MultinomialNB()
    model.fit(x, y)
    w = model.feature_log_prob_
    b = model.class_log_prior_
    return {"w": w.tolist(), "b": b.tolist()}


def _train_tree(manifest: Dict[str, Any], data: Dict[str, Any], max_depth: int | None) -> Dict[str, Any]:
    _require_sklearn()
    import numpy as np  # type: ignore
    from sklearn.tree import DecisionTreeRegressor  # type: ignore

    build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
    node_count = build.get("tree_node_count")
    if not isinstance(node_count, int):
        raise ValueError("build.tree_node_count required for tree training")
    x = np.asarray(data["x"], dtype=np.float32)
    y = np.asarray(data["y"], dtype=np.float32)
    model = DecisionTreeRegressor(max_depth=max_depth)
    model.fit(x, y)
    tree = model.tree_
    nodes = []
    for idx in range(tree.node_count):
        feature = int(tree.feature[idx])
        if feature < 0:
            nodes.append({"feature": -1, "threshold": 0.0, "left": -1, "right": -1, "value": float(tree.value[idx][0][0])})
        else:
            nodes.append(
                {
                    "feature": feature,
                    "threshold": float(tree.threshold[idx]),
                    "left": int(tree.children_left[idx]),
                    "right": int(tree.children_right[idx]),
                    "value": float(tree.value[idx][0][0]),
                }
            )
    if len(nodes) > node_count:
        raise ValueError("trained tree exceeds build.tree_node_count")
    while len(nodes) < node_count:
        nodes.append({"feature": -1, "threshold": 0.0, "left": -1, "right": -1, "value": 0.0})
    return {"nodes": nodes}


def run_train_from_args(args: Any) -> int:
    manifest_path = Path(args.manifest)
    manifest = _load_manifest(manifest_path)
    template = _infer_template(manifest, args.template)

    data = _load_dataset(Path(args.data), template, args.label_col)

    build = manifest.get("build", {}) if isinstance(manifest, dict) else {}
    has_bias = bool(build.get("has_bias", True))
    if args.no_bias:
        has_bias = False

    overrides = {
        "hidden_dim": args.hidden_dim,
        "hidden_dim1": args.hidden_dim1,
        "hidden_dim2": args.hidden_dim2,
        "hidden_dim3": args.hidden_dim3,
        "kernel_size": args.kernel_size,
        "out_channels": args.out_channels,
        "stride": args.stride,
        "input_height": args.input_height,
        "input_width": args.input_width,
        "input_dim_a": args.input_dim_a,
        "input_dim_b": args.input_dim_b,
        "embed_dim": args.embed_dim,
        "no_bias": not has_bias,
    }

    if template == "naive_bayes":
        weights = _train_naive_bayes(manifest, data)
    elif template == "tree":
        weights = _train_tree(manifest, data, args.tree_max_depth)
    else:
        weights = _train_torch(
            template=template,
            manifest=manifest,
            data=data,
            task=args.task,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            seed=args.seed,
            val_split=args.val_split,
            overrides=overrides,
        )

    out_dir = Path(args.output_dir) if args.output_dir else manifest_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / "weights.json"
    weights_path.write_text(json.dumps(weights, indent=2))

    if args.input_calibrate_percentile is not None:
        if "x" in data:
            calib_path = out_dir / "input_calibration.json"
            _write_calibration(calib_path, data["x"], args.input_calibrate_percentile)
        if "x_a" in data and "x_b" in data:
            _write_calibration(out_dir / "input_calibration_a.json", data["x_a"], args.input_calibrate_percentile)
            _write_calibration(out_dir / "input_calibration_b.json", data["x_b"], args.input_calibrate_percentile)

    if not args.no_convert:
        from ..convert import load_and_convert

        scale_args: Dict[str, int] = {}
        if template in ("linear", "softmax", "naive_bayes"):
            scale_args["scale_q16"] = _compute_scale_q16(weights["w"], args.calibrate_percentile)
        elif template == "mlp":
            scale_args["w1_scale_q16"] = _compute_scale_q16(weights["w1"], args.calibrate_percentile)
            scale_args["w2_scale_q16"] = _compute_scale_q16(weights["w2"], args.calibrate_percentile)
        elif template == "mlp2":
            scale_args["w1_scale_q16"] = _compute_scale_q16(weights["w1"], args.calibrate_percentile)
            scale_args["w2_scale_q16"] = _compute_scale_q16(weights["w2"], args.calibrate_percentile)
            scale_args["w3_scale_q16"] = _compute_scale_q16(weights["w3"], args.calibrate_percentile)
        elif template == "mlp3":
            scale_args["w1_scale_q16"] = _compute_scale_q16(weights["w1"], args.calibrate_percentile)
            scale_args["w2_scale_q16"] = _compute_scale_q16(weights["w2"], args.calibrate_percentile)
            scale_args["w3_scale_q16"] = _compute_scale_q16(weights["w3"], args.calibrate_percentile)
            scale_args["w4_scale_q16"] = _compute_scale_q16(weights["w4"], args.calibrate_percentile)
        elif template in ("two_tower", "cnn1d", "tiny_cnn"):
            scale_args["w1_scale_q16"] = _compute_scale_q16(weights["w1"], args.calibrate_percentile)
            scale_args["w2_scale_q16"] = _compute_scale_q16(weights["w2"], args.calibrate_percentile)

        load_and_convert(
            manifest_path=manifest_path,
            input_path=weights_path,
            template=template,
            output_path=None,
            scale_q16=scale_args.get("scale_q16"),
            w1_scale_q16=scale_args.get("w1_scale_q16"),
            w2_scale_q16=scale_args.get("w2_scale_q16"),
            w3_scale_q16=scale_args.get("w3_scale_q16"),
            w4_scale_q16=scale_args.get("w4_scale_q16"),
            update_manifest=True,
            input_dim_override=None,
            output_dim_override=None,
            hidden_dim_override=None,
            hidden_dim1_override=None,
            hidden_dim2_override=None,
            hidden_dim3_override=None,
            bias=has_bias,
            keymap=None,
            input_dim_a_override=None,
            input_dim_b_override=None,
            embed_dim_override=None,
            tree_count_override=None,
            tree_node_count_override=None,
        )

    print(f"Wrote weights: {weights_path}")
    if args.input_calibrate_percentile is not None:
        if "x" in data:
            print(f"Wrote input calibration: {out_dir / 'input_calibration.json'}")
        if "x_a" in data and "x_b" in data:
            print(f"Wrote input calibration: {out_dir / 'input_calibration_a.json'}")
            print(f"Wrote input calibration: {out_dir / 'input_calibration_b.json'}")
    return 0
