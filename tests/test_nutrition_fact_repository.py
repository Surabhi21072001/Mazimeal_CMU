import json

import pytest

from nutrition_fact_repository import NutritionFactRepository

repository = NutritionFactRepository()


def test_seed_counts_per_category():
    assert len(repository.fetch_rule_ids("bioavailability")) == 13
    assert len(repository.fetch_rule_ids("synergy")) == 7


def test_summaries_are_rule_id_name_and_summary_only():
    summaries = repository.fetch_fact_summaries("synergy")
    assert summaries[0].startswith("SYN-001 (Vitamin C with nonheme iron): Human absorption research")
    assert all(line.startswith("SYN-") for line in summaries)


def test_recommended_actions_for_selected_ids_only():
    actions = repository.fetch_recommended_actions(["BIO-002"])
    assert list(actions) == ["BIO-002"]
    assert actions["BIO-002"].code == "PROC_CRUSH_REST"


def test_evidence_sources():
    sources = repository.fetch_evidence_sources(["SYN-001"])
    assert sources["SYN-001"][0].url.startswith("https://ods.od.nih.gov")


def test_unknown_rule_id_raises():
    with pytest.raises(KeyError):
        repository.fetch_recommended_actions(["BIO-999"])


def test_duplicate_rule_id_across_files_raises(tmp_path):
    seed = json.loads(open("data/seed_facts/synergy.json").read())[0]
    (tmp_path / "a.json").write_text(json.dumps([seed]))
    (tmp_path / "b.json").write_text(json.dumps([seed]))
    with pytest.raises(ValueError):
        NutritionFactRepository(tmp_path)
