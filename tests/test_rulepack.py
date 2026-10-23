import copy

import pytest
import yaml
from conftest import PACK

from shodhaka.rules.pack import RulePackError, parse, validate


def raw():
    return yaml.safe_load(PACK.read_text())


def test_acme_pack_is_valid(pack):
    assert pack.pack == "acme-architecture"
    assert [r.id for r in pack.rules] == [f"ARCH-0{i}" for i in range(1, 8)]
    assert {r.method for r in pack.rules} == {"decider", "code"}


def test_rule_needs_exactly_one_check_method():
    data = raw()
    data["rules"][0]["deterministic"] = {"check": "secret_scan"}
    problems = validate(data)
    assert problems and problems[0].startswith("rules/0")


def test_decider_rule_needs_gap_and_compliant_options():
    data = raw()
    for opt in data["rules"][0]["decider"]["options"].values():
        opt["verdict"] = "not_applicable" if opt["verdict"] == "gap" else opt["verdict"]
    assert any("at least one 'gap'" in p for p in validate(data))


def test_duplicate_ids_rejected():
    data = raw()
    data["rules"].append(copy.deepcopy(data["rules"][0]))
    with pytest.raises(RulePackError, match="duplicate"):
        parse(data)


def test_unknown_deterministic_check_rejected():
    data = raw()
    data["rules"][2]["deterministic"]["check"] = "rm_rf"
    assert validate(data)


def test_rules_for_kind(pack):
    assert {r.id for r in pack.rules_for("config")} == {"ARCH-03", "ARCH-06"}
    assert {r.id for r in pack.rules_for("dockerfile")} == {"ARCH-07"}
