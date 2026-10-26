import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.impact import ImpactPlanningError, plan_impact


BASE = "e73d521e8d246691888d656419457d5b0eedd055"


def source(identity, revision, path, **kwargs):
    return {
        "stable_source_id": identity,
        "source_kind": "repository_file",
        "source_revision": revision,
        "source_paths": [path] if path else [],
        "source_locator": path or f"source:{identity}",
        "evidence_refs": [f"evidence:{identity}:{revision}"],
        **kwargs,
    }


def registry(contexts=None):
    return {
        "canonical_store": "git_tracked_repository_artifacts",
        "registry_version": 11,
        "contexts": contexts or [],
        "work_items": [],
    }


def context(context_id, *, status="accepted", version=2, refs=None, claims=None, relationships=None):
    item = {
        "context_id": context_id,
        "context_type": "test",
        "title": context_id,
        "purpose": "Test impact planning.",
        "lifecycle_status": status,
        "version": version,
        "relationships": relationships or [],
        "evidence_refs": refs or [],
        "open_questions": [],
    }
    if claims is not None:
        item["claims"] = claims
    return item


def dep_map(edges=None, reviewed=BASE):
    return {
        "schema_version": "scs.dependency-map.v1",
        "map_version": 11,
        "reviewed_base_commit": reviewed,
        "edges": edges or [],
    }


def edge(source_path, target_path, basis="direct_import", confidence="high", relationship="imports"):
    return {
        "source_path": source_path,
        "target_path": target_path,
        "basis": basis,
        "confidence": confidence,
        "relationship": relationship,
    }


def plan(previous, current, *, contexts=None, edges=None, reviewed=BASE, catalog=None):
    return plan_impact(
        base_commit=BASE,
        registry_snapshot=registry(contexts),
        dependency_map=dep_map(edges, reviewed),
        previous_sources=previous,
        current_sources=current,
        source_catalog=catalog,
    )


class SwarmImpactTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads((ROOT / "schemas/impact-plan.schema.json").read_text())

    def assert_schema_valid(self, result):
        errors = list(Draft202012Validator(self.schema, format_checker=FormatChecker()).iter_errors(result))
        self.assertEqual([], [f"{'/'.join(str(p) for p in error.absolute_path)}: {error.message}" for error in errors])
        self.assertFalse(result["committed"])
        self.assertEqual([], result["external_actions"])

    def test_unchanged_source_replay_is_deterministic_noop(self):
        previous = [source("doc:operating-model", "blob:a", "docs/model.md")]
        result = plan(previous, copy.deepcopy(previous), edges=[edge("src/consumer.py", "docs/model.md")])
        replay = plan(previous, copy.deepcopy(previous), edges=[edge("src/consumer.py", "docs/model.md")])
        self.assert_schema_valid(result)
        self.assertEqual(result["plan_status"], "no_change")
        self.assertEqual(result["source_changes"], [])
        self.assertEqual(result["direct_impacts"], [])
        self.assertEqual(result["possible_impacts"], [])
        self.assertEqual(result["plan_id"], replay["plan_id"])

    def test_changed_revision_traverses_explicit_edge_and_proposes_claim_stale(self):
        previous = [source("doc:operating-model", "blob:a", "docs/model.md")]
        current = [source("doc:operating-model", "blob:b", "docs/model.md")]
        derived = context(
            "ctx-consumer",
            refs=["src/consumer.py"],
            claims=[{
                "claim_id": "claim-consumer",
                "text": "Consumer follows the operating model.",
                "status": "accepted",
                "evidence_refs": ["src/consumer.py"],
            }],
        )
        result = plan(previous, current, contexts=[derived], edges=[
            edge("src/consumer.py", "docs/model.md"),
        ])
        self.assert_schema_valid(result)
        self.assertEqual(result["plan_status"], "proposed")
        self.assertEqual(result["source_changes"][0]["change_kind"], "revision_changed")
        artifact = next(x for x in result["direct_impacts"] if x["target_id"] == "src/consumer.py")
        self.assertEqual(artifact["changed_source_ids"], ["doc:operating-model"])
        self.assertEqual(result["stale_proposals"][0]["target_type"], "claim")
        self.assertEqual(result["stale_proposals"][0]["from_status"], "accepted")
        self.assertEqual(result["stale_proposals"][0]["proposed_status"], "stale")
        self.assertEqual(derived["claims"][0]["status"], "accepted")
        self.assertEqual(derived["version"], 2)

    def test_fanout_reaches_all_explicit_dependents_once(self):
        previous = [source("doc:source", "r1", "docs/source.json")]
        current = [source("doc:source", "r2", "docs/source.json")]
        result = plan(previous, current, edges=[
            edge("src/left.py", "docs/source.json"),
            edge("src/right.py", "docs/source.json"),
            edge("tests/test_left.py", "src/left.py", basis="direct_test_import"),
            edge("tests/test_right.py", "src/right.py", basis="direct_test_import"),
        ])
        self.assert_schema_valid(result)
        artifacts = {x["target_id"] for x in result["direct_impacts"] if x["target_type"] == "artifact"}
        self.assertEqual(artifacts, {"src/left.py", "src/right.py", "tests/test_left.py", "tests/test_right.py"})

    def test_multi_source_impact_set_is_deduplicated_with_union_of_causes(self):
        previous = [
            source("doc:a", "r1", "docs/a.json"),
            source("doc:b", "r1", "docs/b.json"),
        ]
        current = [
            source("doc:a", "r2", "docs/a.json"),
            source("doc:b", "r2", "docs/b.json"),
        ]
        result = plan(previous, current, edges=[
            edge("src/shared.py", "docs/a.json"),
            edge("src/shared.py", "docs/b.json"),
        ])
        self.assert_schema_valid(result)
        matches = [x for x in result["direct_impacts"] if x["target_type"] == "artifact" and x["target_id"] == "src/shared.py"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["changed_source_ids"], ["doc:a", "doc:b"])

    def test_semantic_or_weak_edge_is_possible_not_direct(self):
        previous = [source("doc:core", "r1", "src/core.py")]
        current = [source("doc:core", "r2", "src/core.py")]
        result = plan(previous, current, edges=[
            edge("docs/decision.md", "src/core.py", basis="semantic_contract_relationship",
                 confidence="medium", relationship="describes"),
        ])
        self.assert_schema_valid(result)
        self.assertFalse(any(x["target_id"] == "docs/decision.md" for x in result["direct_impacts"]))
        possible = next(x for x in result["possible_impacts"] if x["target_id"] == "docs/decision.md")
        self.assertEqual(possible["changed_source_ids"], ["doc:core"])

    def test_stale_dependency_map_downgrades_graph_edges_to_possible(self):
        previous = [source("doc:source", "r1", "docs/source.md")]
        current = [source("doc:source", "r2", "docs/source.md")]
        result = plan(previous, current, edges=[edge("src/consumer.py", "docs/source.md")],
                      reviewed="older-base")
        self.assert_schema_valid(result)
        self.assertFalse(result["dependency_map"]["matches_base_commit"])
        self.assertFalse(any(x["target_id"] == "src/consumer.py" for x in result["direct_impacts"]))
        self.assertTrue(any(x["target_id"] == "src/consumer.py" for x in result["possible_impacts"]))

    def test_source_without_exact_path_is_preserved_as_possible_impact(self):
        previous = [source("external:api", "r1", None)]
        current = [source("external:api", "r2", None)]
        result = plan(previous, current, contexts=[context("ctx-api", status="active")],
                      catalog={"sources":[{"source_id":"external:api","context_routes":["ctx-api"]}]})
        self.assert_schema_valid(result)
        self.assertTrue(any(x["target_type"] == "source" and x["target_id"] == "external:api"
                            for x in result["possible_impacts"]))
        self.assertTrue(any(x["target_type"] == "context" and x["target_id"] == "ctx-api"
                            for x in result["possible_impacts"]))
        self.assertEqual(result["stale_proposals"], [])

    def test_context_without_claim_records_gets_stale_version_proposal(self):
        previous = [source("doc:source", "r1", "docs/source.md")]
        current = [source("doc:source", "r2", "docs/source.md")]
        derived = context("ctx-derived", status="accepted", version=4, refs=["docs/source.md"])
        result = plan(previous, current, contexts=[derived])
        self.assert_schema_valid(result)
        proposal = next(x for x in result["stale_proposals"] if x["target_type"] == "context")
        self.assertEqual(proposal["expected_version"], 4)
        self.assertEqual(proposal["proposed_version"], 5)
        self.assertEqual(proposal["from_status"], "accepted")
        self.assertEqual(proposal["proposed_status"], "stale")
        self.assertEqual(derived["lifecycle_status"], "accepted")

    def test_missing_revision_is_unresolved_not_a_no_change(self):
        previous = [source("doc:unknown", None, "docs/unknown.md")]
        result = plan(previous, copy.deepcopy(previous))
        self.assert_schema_valid(result)
        self.assertEqual(result["plan_status"], "review_required")
        self.assertEqual(result["unresolved_source_ids"], ["doc:unknown"])
        self.assertTrue(any(x["target_type"] == "source" and x["target_id"] == "doc:unknown"
                            for x in result["possible_impacts"]))
        self.assertEqual(result["stale_proposals"], [])

    def test_indirect_import_basis_cannot_become_direct_by_substring(self):
        previous = [source("doc:core", "r1", "src/core.py")]
        current = [source("doc:core", "r2", "src/core.py")]
        result = plan(previous, current, edges=[
            edge("docs/decision.md", "src/core.py", basis="indirect_import",
                 confidence="high", relationship="possibly_related"),
        ])
        self.assert_schema_valid(result)
        self.assertFalse(any(x["target_id"] == "docs/decision.md" for x in result["direct_impacts"]))
        self.assertTrue(any(x["target_id"] == "docs/decision.md" for x in result["possible_impacts"]))

    def test_unknown_revision_and_duplicate_identity_fail_closed(self):
        previous = [source("doc:source", None, "docs/source.md"),
                    source("doc:source", "r2", "docs/other.md")]
        with self.assertRaises(ImpactPlanningError):
            plan(previous, [], edges=[])

    def test_dangling_context_relationship_and_escaping_path_fail_closed(self):
        previous = [source("doc:source", "r1", "docs/source.md")]
        current = [source("doc:source", "r2", "docs/source.md")]
        with self.assertRaises(ImpactPlanningError):
            plan(previous, current, contexts=[
                context("ctx-a", relationships=[{"type":"depends_on","target_context_id":"ctx-missing"}])
            ])
        with self.assertRaises(ImpactPlanningError):
            plan(previous, current, edges=[edge("../outside.py", "docs/source.md")])


if __name__ == "__main__":
    unittest.main()
