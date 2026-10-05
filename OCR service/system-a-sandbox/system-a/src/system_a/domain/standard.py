"""Loads the versioned Validation Standard (config/standards/<version>/*.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_ROOT = Path(__file__).resolve().parents[3] / "config"


@dataclass(frozen=True)
class Standard:
    version: str
    ruleset_version: str
    gate_mode: str
    rules: dict
    codes: dict
    policy: dict
    uom_groups: dict
    entities: dict

    # convenience -------------------------------------------------------
    def tol(self, k: str) -> Decimal:
        return Decimal(str(self.policy["tolerance"][k]))

    def rule_version(self, rid: str) -> str:
        return str(self.rules[rid]["version"])

    def code_name(self, code: str) -> str:
        return self.codes[code]["name"]

    def severity(self, code: str) -> str:
        return self.codes[code]["severity"]

    def threshold(self, field_name: str) -> tuple[float, bool]:
        for grp in self.policy["confidence"].values():
            if field_name in grp["fields"]:
                return float(grp["min"]), bool(grp["require_agreement"])
        return 0.70, False

    def uom_group(self, u) -> str | None:
        if u is None:
            return None
        x = str(u).strip().upper().replace(" ", "")
        for g, members in self.uom_groups.items():
            if x in {m.upper() for m in members} or x.rstrip(".") in {m.upper().rstrip(".") for m in members}:
                return g
        return x.rstrip(".") or None


@lru_cache(maxsize=8)
def load_standard(version: str = "v6.6", root: str | None = None) -> Standard:
    base = Path(root or CONFIG_ROOT) / "standards" / version
    rd = lambda n: yaml.safe_load((base / n).read_text(encoding="utf-8"))
    rules, codes = rd("rules.yaml"), rd("codes.yaml")
    ents = {int(k): v for k, v in rd("buyer_entity.yaml")["entities"].items()}
    return Standard(version=codes["standard_version"], ruleset_version=rules["ruleset_version"],
                    gate_mode=rules.get("gate_mode", "standard"), rules=rules["rules"], codes=codes["codes"],
                    policy=rd("policy.yaml"), uom_groups=rd("uom_groups.yaml"), entities=ents)


def load_prompt(name: str, root: str | None = None) -> str:
    return (Path(root or CONFIG_ROOT) / "prompts" / f"{name}.md").read_text(encoding="utf-8")
