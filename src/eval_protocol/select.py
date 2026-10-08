"""Decide whether a change needs an evaluation run, and which layers.

Running the whole suite on every push costs minutes and gets bypassed. The gate
first asks whether the change can move a quality metric at all: it matches the
changed files against declared trigger paths, skips on an exemption label, and
skips when the touched files are byte-identical to a run already recorded.

Config (JSON):

    {
      "layers": ["forecast", "parser", "memory"],
      "triggers": [
        {"paths": ["app/forecast/*"], "layers": ["forecast"]},
        {"paths": ["app/providers/*"], "layers": "all"},
        {"paths": ["prompts/*"], "layers": ["parser", "memory"]}
      ],
      "exempt_label": "eval-exempt"
    }

Patterns use shell globs where `*` also crosses directories.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from .tiers import ProtocolError


@dataclass
class Selection:
    layers: list[str] = field(default_factory=list)
    touched: list[str] = field(default_factory=list)
    skip: bool = False
    reason: str = ""
    cache_key: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def load_config(path: str | Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        layers = list(raw["layers"])
        for t in raw["triggers"]:
            if not t["paths"]:
                raise ValueError("a trigger has no paths")
            if t["layers"] != "all" and not set(t["layers"]) <= set(layers):
                raise ValueError(f"unknown layer in trigger {t['paths']}")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ProtocolError(f"cannot read trigger config {path}: {exc}") from exc
    return raw


def changed_files(base: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProtocolError(f"cannot diff against {base}: {exc}") from exc
    return [line for line in out.splitlines() if line.strip()]


def cache_key(paths: list[str], root: str | Path = ".") -> str:
    """Hash of the touched files' paths and contents. A rebase that changes none of them keeps the key."""
    h = hashlib.sha256()
    for rel in sorted(paths):
        h.update(rel.encode())
        f = Path(root) / rel
        h.update(f.read_bytes() if f.is_file() else b"<deleted>")
    return h.hexdigest()


def select(changed: list[str], config: dict, labels: list[str] | tuple[str, ...] = (),
           cache: dict | None = None, root: str | Path = ".") -> Selection:
    all_layers = list(config["layers"])
    layers: set[str] = set()
    touched: list[str] = []
    for path in changed:
        for trig in config["triggers"]:
            if any(fnmatch(path, pat) for pat in trig["paths"]):
                touched.append(path)
                layers |= set(all_layers) if trig["layers"] == "all" else set(trig["layers"])
    touched = sorted(set(touched))

    if not touched:
        return Selection(skip=True, reason="no trigger path touched: nothing can move a quality metric")

    label = config.get("exempt_label")
    if label and label in labels:
        return Selection(touched=touched, skip=True,
                         reason=f"'{label}' label: a human declared this change cannot move a metric; reviewed, not computed")

    key = cache_key(touched, root)
    if cache and key in cache:
        return Selection(touched=touched, skip=True, cache_key=key,
                         reason="touched files identical to an evaluated run")

    return Selection(layers=[l for l in all_layers if l in layers], touched=touched,
                     reason=f"{len(touched)} trigger file(s) touched", cache_key=key)


def load_cache(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ProtocolError(f"cannot read cache {path}: {exc}") from exc


def record_cache(path: str | Path, key: str, verdict: str) -> None:
    cache = load_cache(path)
    cache[key] = verdict
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
