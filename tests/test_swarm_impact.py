import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jsonschema import Draft202012Validator, FormatChecker
from scs.impact import ImpactPlanningError, plan_context_impact


BASE_COMMIT = "f90d064455bab412e43763fbacd40be60128f0f9"


def load_registry():
    return json.loads((ROOT / "swarm/registry.json").read_text())


def load_dependency_map():
    return json.loads((ROOT / "swarm/dependency-map.json").read_text())


def source(stable_id="repo-file:src/scs/intake.py", previous="sha-old",
           current="sha-new", paths=None, evidence=None):
    return {
        "stable_source_id": stable_id,
        "source_kind": "repository_file",
        "previous_revision": previous,
        "current_revision": current,
        "artifact_paths": paths if paths is not None else ["src/scs/intake.py"],
        "evidence_refs": evidence if evidence is not None else [
            "https://github.com/Loofy147/Context-swarm/commit/" + BASE_COMMIT
        ],
    }


def plan(observations, registry=None, dependency_map=None, base=BASE_COMMIT):
    return plan_context_impact(
        cycle_id="impact-test-001",
        base_commit=base,
        registry_snapshot=registry if registry is not None else load_registry(),
        dependency_map=dependency_map if dependency_map is not None else load_dependency_map(),
        source_observations=observations,
    )


class ContextImpactTests(unittest.TestCase):
    def validate_schema(self, result):
        schema = json.loads((ROOT / "schemas/impact-plan.schema.json").read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(result))
        self.assertEqual(
            [],
            [f"{'/'.join(str(p) for p in error.absolute_path)}: {error.message}" for error in errors],
        )

    def test_no_change_replay_is_deterministic_and_has_no_side_effects(self):
        observation = source(previous="same-rev", current="same-rev")
        result_a = plan([observation])
        result_b = plan([observation])
        self.assertEqual(result_a, result_b)
        self.assertEqual(result_a["plan_status"], "no_change")
        self.assertEqual(result_a["direct_impacts"], [])
        self.assertEqual(result_a["possible_impacts"], [])
        self.assertEqual(result_a["stale_proposals"], [])
        self.assertFalse(result_a["committed"])
        self.assertEqual(result_a["external_actions"], [])
        self.validate_schema(result_a)

    def test_changed_revision_proposes_stale_without_mutating_history(self):
        registry = load_registry()
        before = copy.deepcopy(registry)
        result = plan([source()], registry=registry)
        self.assertEqual(registry, before)
        self.assertEqual(result["plan_status"], "proposed")
        direct_contexts = {item["target_id"] for item in result["direct_impacts"]
                           if item["target_type"] == "context"}
        self.assertIn("ctx-scs-intake", direct_contexts)
        proposal = next(item for item in result["stale_proposals"]
                        if item["context_id"] == "ctx-scs-intake")
        self.assertEqual(proposal["from_status"], "accepted")
        self.assertEqual(proposal["to_status"], "stale")
        self.assertEqual(proposal["result_version"], proposal["base_version"] + 1)
        self.assertTrue(proposal["evidence_refs"])
        self.assertFalse(result["committed"])
        self.validate_schema(result)

    def test_explicit_dependency_fanout_reaches_artifacts_and_dependent_contexts(self):
        result = plan([source()])
        direct_artifacts = {item["target_id"] for item in result["direct_impacts"]
                            if item["target_type"] == "artifact"}
        direct_contexts = {item["target_id"] for item in result["direct_impacts"]
                           if item["target_type"] == "context"}
        self.assertIn("src/scs/cycle.py", direct_artifacts)
        self.assertIn("tests/test_swarm_cycle.py", direct_artifacts)
        self.assertIn("ctx-scs-intake", direct_contexts)
        self.assertIn("ctx-scs-repository-demo", direct_contexts)
        self.assertIn("ctx-scs-source-catalog", direct_contexts)
        self.assertIn("ctx-scs-repository-observation", direct_contexts)
        self.validate_schema(result)

    def test_multiple_changed_sources_deduplicate_and_merge_provenance(self):
        result = plan([
            source("repo-file:intake", paths=["src/scs/intake.py"]),
            source("repo-file:cycle", paths=["src/scs/cycle.py"]),
        ])
        artifact_matches = [item for item in result["direct_impacts"]
                            if item["target_type"] == "artifact"
                            and item["target_id"] == "tests/test_swarm_cycle.py"]
        self.assertEqual(len(artifact_matches), 1)
        self.assertEqual(
            set(artifact_matches[0]["source_ids"]),
            {"repo-file:intake", "repo-file:cycle"},
        )
        self.assertEqual(
            len({(item["target_type"], item["target_id"]) for item in result["direct_impacts"]}),
            len(result["direct_impacts"]),
        )
        self.validate_schema(result)

    def test_semantic_dependency_is_possible_not_direct(self):
        result = plan([source(paths=["swarm/dependency-map.json"])])
        direct = {(item["target_type"], item["target_id"]) for item in result["direct_impacts"]}
        possible = {(item["target_type"], item["target_id"]) for item in result["possible_impacts"]}
        self.assertIn(("artifact", "swarm/registry.json"), possible)
        self.assertNotIn(("artifact", "swarm/registry.json"), direct)
        self.assertTrue(any("planned_registry_link" in ref
                            for item in result["possible_impacts"] for ref in item["edge_refs"]))
        self.validate_schema(result)

    def test_stale_dependency_map_blocks_direct_artifact_claims(self):
        dependency_map = load_dependency_map()
        dependency_map["reviewed_base_commit"] = "d8482f02af7a7e11487491869948cad91037e1d7"
        result = plan([source()], dependency_map=dependency_map)
        direct_artifacts = {item["target_id"] for item in result["direct_impacts"]
                            if item["target_type"] == "artifact"}
        possible_artifacts = {item["target_id"] for item in result["possible_impacts"]
                              if item["target_type"] == "artifact"}
        self.assertEqual(result["plan_status"], "blocked")
        self.assertFalse(result["dependency_map_fresh"])
        self.assertNotIn("src/scs/cycle.py", direct_artifacts)
        self.assertIn("src/scs/cycle.py", possible_artifacts)
        self.assertTrue(result["blockers"])
        self.validate_schema(result)

    def test_verified_claim_with_changed_evidence_is_only_proposed_stale(self):
        registry = load_registry()
        context = next(item for item in registry["contexts"]
                       if item["context_id"] == "ctx-scs-intake")
        context["claims"] = [{
            "claim_id": "claim-intake-verified",
            "text": "The intake module is current.",
            "status": "verified",
            "evidence_refs": ["src/scs/intake.py"],
        }]
        result = plan([source()], registry=registry)
        claim = next(item for item in result["stale_claim_proposals"]
                     if item["claim_id"] == "claim-intake-verified")
        self.assertEqual(claim["from_status"], "verified")
        self.assertEqual(claim["to_status"], "stale")
        self.assertIn("src/scs/intake.py", claim["evidence_refs"])
        self.assertFalse(result["committed"])
        self.assertEqual(context["claims"][0]["status"], "verified")
        self.validate_schema(result)

    def test_missing_path_mapping_blocks_instead_of_claiming_no_impact(self):
        result = plan([source(paths=[])])
        self.assertEqual(result["plan_status"], "blocked")
        self.assertTrue(any("no artifact_paths mapping" in value for value in result["blockers"]))
        self.assertFalse(result["committed"])
        self.validate_schema(result)

    def test_dangling_context_relationship_is_rejected(self):
        registry = load_registry()
        registry["contexts"][0]["relationships"].append({
            "type": "depends_on",
            "target_context_id": "ctx-does-not-exist",
        })
        with self.assertRaises(ImpactPlanningError):
            plan([source()], registry=registry)

    def test_duplicate_stable_source_identity_is_rejected(self):
        with self.assertRaises(ImpactPlanningError):
            plan([
                source("repo-file:same", paths=["src/scs/intake.py"]),
                source("repo-file:same", paths=["src/scs/cycle.py"]),
            ])

    def test_revision_without_a_stable_source_identity_or_known_revision_is_rejected(self):
        bad = source()
        bad["stable_source_id"] = ""
        with self.assertRaises(ImpactPlanningError):
            plan([bad])
        bad = source()
        bad["current_revision"] = None
        with self.assertRaises(ImpactPlanningError):
            plan([bad])


if __name__ == "__main__":
    unittest.main()
