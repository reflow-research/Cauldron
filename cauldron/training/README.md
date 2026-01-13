# Cauldron Training Harness

This starter trains a small model, calibrates weights, and exports
`weights.json` (and optionally `weights.bin`).

## Usage

```
cauldron train --manifest frostbite-model.toml --data data.csv \
  --template mlp --epochs 50 --calibrate-percentile 99.5
```

## Dataset formats

- `.csv` with feature columns + a label column (default: last column)
- `.npz` with arrays:
  - `x` and `y` for most templates
  - `x_a`, `x_b`, and `y` for two_tower

## Calibration helpers

- `--calibrate-percentile` sets weight scales using a percentile of absolute
  weights (reduces outlier impact).
- `--input-calibrate-percentile` writes `input_calibration.json` with a
  suggested clip range for raw inputs.

## Optional deps

```
pip install "frostbite-modelkit[train]"
```

## Classification note

For multi-class classification, set `schema.output_shape` to the number of
classes so the training harness matches the manifest dimensions.
