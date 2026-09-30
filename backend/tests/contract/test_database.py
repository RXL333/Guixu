from pathlib import Path
import json
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from guixu.infrastructure.db.database import Database


def test_initial_schema_and_pragmas(project_root: Path, tmp_path: Path):
    database = Database(tmp_path / "db" / "test.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    with database.engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert {"tasks", "files", "plans", "operations", "privacy_consents"} <= tables
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
        call_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(model_calls)")}
        assert "conversation_id" in call_columns
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    database.close()


def test_alembic_initial_migration_creates_contract_schema(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "migration.sqlite3"
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"alembic_version", "tasks", "files", "operations", "conversations", "conversation_messages", "conversation_contexts"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0012"
        assert "conversation_id" in {row[1] for row in connection.execute("PRAGMA table_info(model_calls)")}
        assert connection.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 12
        plan_columns = {row[1] for row in connection.execute("PRAGMA table_info(plans)")}
        assert {"plan_basis_revision", "approved_task_revision"} <= plan_columns
        version_columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_plan_versions)")}
        assert {"kept_file_count", "conflict_count", "created_by_message_id", "restored_from_version_id",
                "baseline_execution_round_id", "plan_kind"} <= version_columns
        file_columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_files)")}
        assert "current_category_id" in file_columns
        assert {"conversation_plan_approvals", "conversation_message_file_references"} <= tables
        task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert {"deleted_at", "deletion_source", "delete_reason", "conversation_id", "conversation_plan_version_id"} <= task_columns
    finally:
        connection.close()


def test_alembic_v4_to_v5_plan_versioning_upgrade_is_repeatable(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "incremental.sqlite3"
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0004")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 4
        # The base contract is intentionally forward-compatible, so v4 can
        # already contain nullable v5 columns; 0005 must still be idempotent.
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_plan_versions'").fetchone()
    finally:
        connection.close()
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0012"
        assert connection.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 12
        columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_plan_versions)")}
        assert {"kept_file_count", "conflict_count", "created_by_message_id", "restored_from_version_id",
                "baseline_execution_round_id", "plan_kind"} <= columns
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_plan_approvals'").fetchone()
    finally:
        connection.close()
    command.upgrade(config, "head")


def test_v2_to_v7_migration_is_backed_up_and_repeatable(project_root: Path, tmp_path: Path):
    path = tmp_path / "data" / "legacy.sqlite3"
    database = Database(path, project_root / "contracts" / "database.sql")
    database.initialize()
    backups_before = len(list((path.parent / "backups").glob("legacy-schema-*.sqlite3")))
    with database.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE schema_metadata SET version=2")
        definition = json.dumps({"template_id":"legacy.course","version":1,"name":"旧模板","nodes":[]}, ensure_ascii=False)
        connection.exec_driver_sql(
            "INSERT INTO template_versions(id,template_key,version,name,origin,definition_json,definition_hash,created_at) VALUES(?,?,?,?,?,?,?,datetime('now'))",
            ("legacy-template", "legacy.course", 1, "旧模板", "builtin", definition, "a" * 64),
        )
        connection.exec_driver_sql(
            """INSERT INTO tasks(id,name,status,phase,revision,settings_json,settings_hash,classification_request_json,
               template_snapshot_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))""",
            ("legacy-task", "旧任务", "DRAFT", "SETUP", 1, "{}", "b" * 64,
             json.dumps({"template_key":"legacy.course"}), "{}"),
        )
    database.close()

    upgraded = Database(path, project_root / "contracts" / "database.sql")
    upgraded.initialize()
    with upgraded.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar_one() == 12
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
        assert {"deleted_at", "deletion_source", "delete_reason", "conversation_id", "conversation_plan_version_id"} <= columns
        tables = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversations", "conversation_plan_versions", "conversation_plan_approvals", "conversation_execution_rounds", "conversation_message_file_references", "file_evidence"} <= tables
        snapshot = connection.exec_driver_sql(
            "SELECT template_snapshot_json FROM tasks WHERE id='legacy-task'"
        ).scalar_one()
        assert json.loads(snapshot)["name"] == "旧模板"
    backups = list((path.parent / "backups").glob("legacy-schema-*.sqlite3"))
    assert len(backups) == backups_before + 1 and all(item.stat().st_size > 0 for item in backups)
    upgraded.initialize()
    assert len(list((path.parent / "backups").glob("legacy-schema-*.sqlite3"))) == backups_before + 1
    upgraded.close()


LEGACY_MODEL_CALLS = """CREATE TABLE model_calls (
 id TEXT PRIMARY KEY,
 task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
 provider_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('probe','policy','caption','planning','classification','repair')),
 model_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 response_status TEXT NOT NULL CHECK(response_status IN ('ok','error','cancelled')),
 input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
 output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
 estimated_cost_micros INTEGER CHECK(estimated_cost_micros IS NULL OR estimated_cost_micros >= 0),
 currency TEXT, latency_ms INTEGER NOT NULL CHECK(latency_ms >= 0),
 error_code TEXT, created_at TEXT NOT NULL
)"""


def test_v11_chat_audit_migration_preserves_calls_and_classification_links(project_root: Path, tmp_path: Path):
    """Upgrade a genuine v11 database and prove the audit trail survives the rebuild.

    Rebuilding `model_calls` is the only migration that drops a table other tables
    point at. With foreign keys left enabled, `DROP TABLE` fires
    `classifications.model_call_id ON DELETE SET NULL` and silently destroys the link
    between a classification and the call that produced it — so assert it directly.
    """
    path = tmp_path / "data" / "legacy-v11.sqlite3"
    database = Database(path, project_root / "contracts" / "database.sql")
    database.initialize()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE model_calls")
        connection.exec_driver_sql(LEGACY_MODEL_CALLS)
        connection.exec_driver_sql(
            "INSERT INTO model_profiles(id,name,provider,runtime,base_url,model_id,secret_ref,capabilities_json,options_json,trust_scope,enabled,revision,created_at,updated_at)"
            " VALUES('profile','本地模型','deepseek','deepseek','https://api.deepseek.com','deepseek-chat',NULL,'{}','{}','cloud',1,1,datetime('now'),datetime('now'))")
        connection.exec_driver_sql(
            "INSERT INTO tasks(id,name,status,phase,revision,settings_json,settings_hash,classification_request_json,created_at,updated_at)"
            " VALUES('task','旧任务','DRAFT','SETUP',1,'{}','" + "b" * 64 + "','{}',datetime('now'),datetime('now'))")
        connection.exec_driver_sql(
            "INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name)"
            " VALUES('scope','task','whole_tree','C:/src','C:/dst','全部')")
        connection.exec_driver_sql(
            "INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,extension,modality,size_bytes,mtime_ns,sha256,scan_status,created_at,updated_at)"
            " VALUES('file','task','scope','C:/src/a.jpg','C:/src/a.jpg','c:/src/a.jpg','a.jpg','a.jpg','.jpg','image',10,1,'"
            + "c" * 64 + "','eligible',datetime('now'),datetime('now'))")
        connection.exec_driver_sql(
            "INSERT INTO taxonomies(id,task_id,scope_id,version,source,status,tree_hash,created_at)"
            " VALUES('tax','task','scope',1,'auto','approved','" + "d" * 64 + "',datetime('now'))")
        connection.exec_driver_sql(
            "INSERT INTO categories(taxonomy_id,category_id,name,path_segments_json,depth,ordinal,definition_json)"
            " VALUES('tax','cat','照片','[\"照片\"]',1,0,'{}')")
        connection.exec_driver_sql(
            "INSERT INTO model_calls(id,task_id,provider_profile_id,purpose,model_id,request_hash,response_status,input_tokens,output_tokens,latency_ms,created_at)"
            " VALUES('call','task','profile','classification','deepseek-chat','" + "e" * 64 + "','ok',100,20,1234,datetime('now'))")
        connection.exec_driver_sql(
            "INSERT INTO classifications(id,task_id,file_id,taxonomy_id,category_id,attempt,source,review_band,abstain,reason,evidence_refs_json,warnings_json,model_call_id,input_hash,created_at)"
            " VALUES('cls','task','file','tax','cat',1,'ai','high',0,'模型判定','[]','[]','call','" + "f" * 64 + "',datetime('now'))")
        connection.exec_driver_sql("UPDATE schema_metadata SET version=11 WHERE singleton=1")
    database.close()

    upgraded = Database(path, project_root / "contracts" / "database.sql")
    upgraded.initialize()
    with upgraded.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar_one() == 12
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert connection.exec_driver_sql(
            "SELECT purpose,input_tokens,output_tokens FROM model_calls WHERE id='call'"
        ).one() == ("classification", 100, 20)
        # The link from a classification back to its model call must survive the drop.
        assert connection.exec_driver_sql(
            "SELECT model_call_id FROM classifications WHERE id='cls'"
        ).scalar_one() == "call"
        assert "conversation_id" in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(model_calls)")}
        indexes = {row[0] for row in connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='model_calls'")}
        assert {"idx_model_calls_task_created", "idx_model_calls_conversation_created"} <= indexes
    # Discussion is the first model purpose that has no Task behind it.
    with upgraded.engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO model_calls(id,task_id,conversation_id,provider_profile_id,purpose,model_id,request_hash,response_status,input_tokens,output_tokens,latency_ms,created_at)"
            " VALUES('chat',NULL,NULL,'profile','chat','deepseek-chat','" + "a" * 64 + "','ok',7,9,42,datetime('now'))")
    upgraded.initialize()
    upgraded.close()
