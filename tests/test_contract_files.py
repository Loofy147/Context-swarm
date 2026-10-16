import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContractArtifactTests(unittest.TestCase):
    def test_context_schema_declares_version_and_lifecycle(self):
        schema = json.loads((ROOT / "schemas/context.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema_version"]["const"], "scs.context.v1")
        self.assertEqual(set(schema["properties"]["lifecycle_status"]["enum"]),
                         {"draft", "active", "blocked", "archived", "superseded"})
        self.assertIn("content_digest", schema["required"])

    def test_event_schema_has_causality_and_digest(self):
        schema = json.loads((ROOT / "schemas/event.schema.json").read_text())
        props = schema["properties"]
        self.assertIn("causation_ref", props)
        self.assertIn("correlation_ref", props)
        self.assertIn("payload_digest", props)

    def test_sql_migration_has_core_tables_and_outbox_primitives(self):
        sql = (ROOT / "migrations/001_initial_postgres.sql").read_text().lower()
        for table in ["scs_contexts", "scs_context_versions", "scs_events",
                      "scs_outbox", "scs_grants", "scs_approvals", "scs_artifacts"]:
            self.assertIn(f"create table {table}", sql)
        self.assertIn("begin;", sql)
        self.assertIn("commit;", sql)

    def test_openapi_has_versioned_core_operations(self):
        api = (ROOT / "spec/openapi.yaml").read_text()
        for token in ["/contexts:", "createContext", "proposeChange",
                      "commitChange", "coordinateChanges", "getEventHistory"]:
            self.assertIn(token, api)


if __name__ == "__main__":
    unittest.main()
