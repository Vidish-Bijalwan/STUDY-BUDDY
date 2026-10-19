"""Community data-pack loader (PROD-10).

Packs are validated data directories (YAML/JSON) loaded at startup from
``data/packs/<pack-name>/``. Schema-checked; **no code execution** — pack
files are never imported, eval'd, or exec'd, and YAML is parsed with
``yaml.safe_load`` only.

Pack layout::

    data/packs/<pack-name>/
        pack.yaml          # manifest: name, version, kind, license, ...
        data.json|data.yaml  # the payload (schema depends on kind)

Supported kinds: role_profile, question_bank, roadmap, skill_aliases.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "packs"

SUPPORTED_KINDS = ("role_profile", "question_bank", "roadmap", "skill_aliases")

_MANIFEST_REQUIRED = ("name", "version", "kind", "license")


def _manifest_errors(manifest: dict) -> list[str]:
    errors: list[str] = []
    for key in _MANIFEST_REQUIRED:
        if not manifest.get(key):
            errors.append(f"manifest missing required field: {key}")
    kind = manifest.get("kind")
    if kind and kind not in SUPPORTED_KINDS:
        errors.append(f"unknown kind '{kind}'; expected one of {SUPPORTED_KINDS}")
    if manifest.get("version") and not isinstance(manifest["version"], str):
        errors.append("manifest.version must be a string")
    return errors


def _payload_errors(kind: str, payload: Any) -> list[str]:
    if kind == "role_profile":
        if not isinstance(payload, dict):
            return ["role_profile payload must be a mapping"]
        errs = []
        for key in ("title", "skills"):
            if key not in payload:
                errs.append(f"role_profile missing '{key}'")
        if "skills" in payload and not isinstance(payload["skills"], list):
            errs.append("role_profile.skills must be a list")
        return errs
    if kind == "question_bank":
        if not isinstance(payload, list):
            return ["question_bank payload must be a list of items"]
        errs = []
        seen: set[str] = set()
        for i, item in enumerate(payload):
            if not isinstance(item, dict):
                errs.append(f"item {i}: must be a mapping")
                continue
            if not item.get("question"):
                errs.append(f"item {i}: missing 'question'")
            qid = item.get("id")
            if qid:
                if qid in seen:
                    errs.append(f"item {i}: duplicate id '{qid}'")
                seen.add(qid)
        return errs
    if kind == "roadmap":
        if not isinstance(payload, dict) or "stages" not in payload:
            return ["roadmap payload must be a mapping with 'stages'"]
        if not isinstance(payload["stages"], list):
            return ["roadmap.stages must be a list"]
        return []
    if kind == "skill_aliases":
        if not isinstance(payload, dict):
            return ["skill_aliases payload must be a mapping canonical -> [aliases]"]
        return [
            f"skill_aliases['{k}'] must be a list"
            for k, v in payload.items()
            if not isinstance(v, list)
        ]
    return [f"unsupported kind: {kind}"]


def load_pack(pack_dir: str | Path) -> dict:
    """Load and validate one pack. Returns {manifest, data, errors}.

    `errors` non-empty means the pack is rejected (caller skips loading it).
    """
    p = Path(pack_dir)
    manifest_file = p / "pack.yaml"
    if not manifest_file.is_file():
        return {"manifest": {}, "data": None, "errors": [f"missing {manifest_file}"]}
    try:
        manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return {"manifest": {}, "data": None, "errors": [f"pack.yaml invalid: {exc}"]}
    if not isinstance(manifest, dict):
        return {"manifest": {}, "data": None, "errors": ["pack.yaml must be a mapping"]}

    errors = _manifest_errors(manifest)
    data = None
    for fname in ("data.json", "data.yaml", "data.yml"):
        f = p / fname
        if f.is_file():
            try:
                data = (
                    json.loads(f.read_text(encoding="utf-8"))
                    if fname.endswith(".json")
                    else yaml.safe_load(f.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, yaml.YAMLError) as exc:
                errors.append(f"{fname} invalid: {exc}")
            break
    if data is None and not errors:
        errors.append("pack has no data.json/data.yaml payload")
    if not errors:
        errors = _payload_errors(manifest["kind"], data)
    return {"manifest": manifest, "data": data, "errors": errors}


def load_all_packs(packs_dir: str | Path | None = None) -> dict[str, dict]:
    """Load every valid pack under packs_dir; skip (and report) invalid ones."""
    root = Path(packs_dir) if packs_dir else PACKS_DIR
    loaded: dict[str, dict] = {}
    if not root.is_dir():
        return loaded
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        result = load_pack(child)
        if result["errors"]:
            loaded[child.name] = {"ok": False, "errors": result["errors"]}
        else:
            loaded[child.name] = {
                "ok": True,
                "manifest": result["manifest"],
                "data": result["data"],
            }
    return loaded


__all__ = ["PACKS_DIR", "SUPPORTED_KINDS", "load_pack", "load_all_packs"]
