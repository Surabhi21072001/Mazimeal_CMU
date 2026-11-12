"""All database access. No LM. For now the database is the seed JSON files."""
import json
from pathlib import Path

from domain_models import EvidenceSource, NutritionFact, RecommendedAction

DEFAULT_FACTS_DIRECTORY = Path(__file__).parent / "data" / "seed_facts"


class NutritionFactRepository:
    def __init__(self, facts_directory: Path = DEFAULT_FACTS_DIRECTORY):
        self._facts_by_rule_id: dict[str, NutritionFact] = {}
        for facts_file in sorted(facts_directory.glob("*.json")):
            for record in json.loads(facts_file.read_text()):
                fact = NutritionFact(**record)
                if fact.rule_id in self._facts_by_rule_id:
                    raise ValueError(f"duplicate rule_id {fact.rule_id} in {facts_file.name}")
                self._facts_by_rule_id[fact.rule_id] = fact

    def fetch_rule_ids(self, category: str) -> list[str]:
        return [fact.rule_id for fact in self._facts_in(category)]

    def fetch_rule_names(self, category: str) -> dict[str, str]:
        return {fact.rule_id: fact.rule_name for fact in self._facts_in(category)}

    def fetch_fact_summaries(self, category: str) -> list[str]:
        """One 'rule_id (rule name): evidence summary' line per fact. This is all a selector sees."""
        return [
            f"{fact.rule_id} ({fact.rule_name}): {fact.evidence.summary}"
            for fact in self._facts_in(category)
        ]

    def fetch_recommended_actions(self, rule_ids: list[str]) -> dict[str, RecommendedAction]:
        """Raises KeyError for an unknown rule_id."""
        return {rule_id: self._facts_by_rule_id[rule_id].action for rule_id in rule_ids}

    def fetch_evidence_sources(self, rule_ids: list[str]) -> dict[str, list[EvidenceSource]]:
        """Raises KeyError for an unknown rule_id."""
        return {rule_id: self._facts_by_rule_id[rule_id].evidence.sources for rule_id in rule_ids}

    def _facts_in(self, category: str) -> list[NutritionFact]:
        return [fact for fact in self._facts_by_rule_id.values() if fact.category == category]
