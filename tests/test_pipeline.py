"""End-to-end pipeline test with a fake source and a fake LLM (no network)."""

import pandas as pd

from propscout import pipeline
from propscout.agents.llm import _extract_json
from propscout.agents.parser import parse_prompt
from propscout.config import Settings
from propscout.export import render_markdown
from propscout.models import Analysis, SearchQuery, Strategy


class FakeSource:
    name = "fake"

    def search(self, q):
        return pd.DataFrame(
            {
                "property_id": ["a", "b", "b", "c"],
                "formatted_address": ["1 Good St", "2 Meh St", "2 Meh St", "3 Bad St"],
                "property_url": ["u1", "u2", "u2", "u3"],
                "zip_code": ["10001"] * 4,
                "list_price": [200_000, 400_000, 400_000, 0],
                "beds": [3, 3, 3, 3],
                "full_baths": [2, 2, 2, 2],
                "sqft": [1500, 1500, 1500, 1500],
                "estimated_value": [240_000, 380_000, 380_000, None],
                "days_on_mls": [90, 3, 3, 1],
                "text": ["Cozy cabin with views", "", "", ""],
            }
        )

    def rent_comps(self, q):
        return pd.DataFrame(
            {
                "zip_code": ["10001"] * 3,
                "beds": [3, 3, 3],
                "list_price": [2000, 2100, 2200],
                "style": ["SINGLE_FAMILY"] * 3,
            }
        )

    def sold_comps(self, q, past_days=180):
        raise RuntimeError("blocked")  # pipeline must survive comp failures


class FakeLLM:
    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, schema):
        self.calls.append(user)
        if schema is SearchQuery:
            return SearchQuery(location="Asheville, NC", price_max=500_000, strategies=["str"])
        score = 9 if "Good St" in user else 4
        return Analysis(score=score, best_strategy=Strategy.LTR, thesis="t", risks=["r"])


def test_pipeline_end_to_end():
    llm = FakeLLM()
    q = SearchQuery(location="Anywhere", strategies=[Strategy.LTR])
    res = pipeline.run(q, FakeSource(), Settings(_env_file=None), llm=llm, analyze_top=5)
    df = res.df
    assert list(df["formatted_address"]) == ["1 Good St", "2 Meh St"]  # deduped, $0 dropped
    assert list(df["rank"]) == [1, 2]
    assert df.loc[0, "ai_score"] == 9
    assert df.loc[0, "est_rent"] == 2100
    assert df.loc[0, "cap_rate"] > df.loc[1, "cap_rate"]
    assert any("Sold comps unavailable" in w for w in res.warnings)
    assert res.analyzed == 2
    assert "Cozy cabin" in llm.calls[0] or "Cozy cabin" in llm.calls[1]
    md = render_markdown(res)
    assert "1 Good St" in md and "Analyst notes" in md


def test_pipeline_without_llm():
    q = SearchQuery(location="Anywhere")
    res = pipeline.run(q, FakeSource(), Settings(_env_file=None), llm=None)
    assert "ai_score" not in res.df.columns
    assert res.df["prescore"].notna().all()


def test_parse_prompt_uses_schema():
    q = parse_prompt(FakeLLM(), "cabin near asheville under 500k for airbnb")
    assert q.price_max == 500_000 and q.strategies == [Strategy.STR]


def test_extract_json_handles_fences_and_prose():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert _extract_json('Sure! {"a": {"b": 2}} hope that helps') == '{"a": {"b": 2}}'


def test_rent_confidence_labels():
    assert pipeline.rent_confidence("zip+beds (n=3)") == "high"
    assert pipeline.rent_confidence("area+beds (n=5)") == "medium"
    assert pipeline.rent_confidence("zip houses (n=4)") == "low"
    assert pipeline.rent_confidence("insufficient_comps") == "none"


def test_land_gets_no_rent():
    class LandSource(FakeSource):
        def search(self, q):
            df = super().search(q)
            df["style"] = "LAND"
            df["beds"] = None
            df["sqft"] = None
            return df

    res = pipeline.run(SearchQuery(location="x"), LandSource(), Settings(_env_file=None))
    assert res.df["est_rent"].isna().all()
    assert (res.df["rent_confidence"] == "n/a").all()
    assert not any("Thin rental market" in w for w in res.warnings)
