import pathlib
import sys

# Make `adapters` / `harness` importable when the harness dir is not on sys.path
# (these tests run offline: no GPU, no network, no heavy deps).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
