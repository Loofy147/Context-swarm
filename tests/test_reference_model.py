import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scs.reference_model import ReferenceStore, ConflictError, AuthorizationError, Lifecycle


class ReferenceModelAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.store = ReferenceStore()
        self.ctx = self.store.create("repo-architecture", "alice")

    def test_context_identity_is_unique(self):
        with self.assertRaises(ConflictError):
            self.store.create("repo-architecture", "bob")

    def test_compare_and_swap_rejects_stale_write(self):
        self.store.commit(self.ctx.context_id, "alice", 1, {"decision": "A"}, can_write=True)
        with self.assertRaises(ConflictError):
            self.store.commit(self.ctx.context_id, "bob", 1, {"decision": "B"}, can_write=True)
        self.assertEqual(self.ctx.current_version, 2)
        self.assertEqual(self.ctx.versions[2].content["decision"], "A")

    def test_committed_versions_are_not_mutated_by_input_changes(self):
        content = {"nested": {"items": [1]}}
        self.store.commit(self.ctx.context_id, "alice", 1, content, can_write=True)
        content["nested"]["items"].append(2)
        self.assertEqual(self.ctx.versions[2].content["nested"]["items"], [1])

    def test_denied_write_does_not_change_state(self):
        with self.assertRaises(AuthorizationError):
            self.store.commit(self.ctx.context_id, "mallory", 1, {"x": 1}, can_write=False)
        self.assertEqual(self.ctx.current_version, 1)
        self.assertEqual(len(self.ctx.events), 1)

    def test_self_approval_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            self.store.approve("release-1", "alice", "alice", authorized_approver=True)
        self.assertNotIn("release-1", self.store.approvals)

    def test_unauthorized_approver_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            self.store.approve("release-1", "alice", "bob", authorized_approver=False)

    def test_external_effect_requires_approval_and_current_authorization(self):
        with self.assertRaises(AuthorizationError):
            self.store.execute_external("release-1", "alice", currently_authorized=True)
        self.store.approve("release-1", "alice", "bob", authorized_approver=True)
        with self.assertRaises(AuthorizationError):
            self.store.execute_external("release-1", "alice", currently_authorized=False)
        self.assertEqual(self.store.external_effects, [])
        self.store.execute_external("release-1", "alice", currently_authorized=True)
        self.assertEqual(len(self.store.external_effects), 1)

    def test_lifecycle_vocabulary_is_explicit(self):
        self.assertEqual({x.value for x in Lifecycle},
                         {"draft", "active", "blocked", "archived", "superseded"})


if __name__ == "__main__":
    unittest.main()
