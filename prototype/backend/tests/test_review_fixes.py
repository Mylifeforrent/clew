"""Review-fix regressions (R1-R7): edge uniqueness, mixed field edges, rollback foreign-key conflicts,
immediate role effect, manifest row-level parse errors, same-pair merging and re-import idempotency,
upload hardening."""

import json
import sqlite3

from lineagelite.config import db_path

from tests.conftest import csv_bytes, create_user, login, upload
from tests.fixtures import order_xlsx_bytes, source_json_bytes, user_csv_bytes


def _seed_sources(client, headers) -> None:
    upload(client, headers, [
        ("order_details.xlsx", order_xlsx_bytes(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("users.csv", user_csv_bytes(), "text/csv"),
        ("source.json", source_json_bytes(), "application/json"),
    ])


def _import_json(client, headers, manifest: dict):
    return client.post("/import", headers=headers,
                       data={"format": "json", "source_file_ids": "1,2,3"},
                       files={"manifest": ("manifest.json",
                                           json.dumps(manifest, ensure_ascii=False).encode(),
                                           "application/json")})


def _import_csv(client, headers, ds_rows, edge_rows):
    return client.post("/import", headers=headers,
                       data={"format": "csv", "source_file_ids": "1,2,3"},
                       files={
                           "manifest_datasets": ("datasets.csv", csv_bytes(ds_rows), "text/csv"),
                           "manifest_lineage": ("lineage.csv", csv_bytes(edge_rows), "text/csv"),
                       })


def _db() -> sqlite3.Connection:
    return sqlite3.connect(db_path())


def _ods_user_manifest(transform: str = "trim") -> dict:
    return {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name", "transform": transform},
        ],
    }


# ---------- R1: uniqueness of table-level/field-level edges (partial unique indexes) ----------

def test_r1_duplicate_edges_blocked_by_partial_unique_index(client):
    login(client)  # Trigger init_db to create the database and indexes
    ins = ("INSERT INTO edge(from_dataset, from_field, to_dataset, to_field,"
           " source, created_at, updated_at) VALUES (?,?,?,?,?,?,?)")
    ts = "2026-01-01T00:00:00+00:00"
    for key in [("A", None, "B", None),  # table-level edge: UNIQUE columns contain NULL, caught by uq_edge_table
                ("A", "f", "B", "g")]:   # field-level edge: caught by uq_edge_field
        conn = _db()
        conn.execute(ins, (*key, "manual", ts, ts))
        try:
            conn.execute(ins, (*key, "manual", ts, ts))
            dup_ok = True
        except sqlite3.IntegrityError:
            dup_ok = False
        finally:
            conn.close()
        assert not dup_ok, f"Duplicate edge for natural key {key} was not blocked"


# ---------- R2: mixed field edges rejected as a whole row ----------

def test_r2_mixed_field_edge_rejected(client):
    headers = login(client)
    _seed_sources(client, headers)
    ds_rows = [
        ["dataset_id", "dataset_name", "field_name", "field_type", "src_file",
         "src_type", "src_locator", "description"],
        ["ods_raw", "Order Details", "order_no", "STRING", "order_details.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "header_path": ["Product Info", "Order No"],
                     "header_rows": 2, "row_start": 3}), "Order No"],
        ["dwd_order", "Order Wide Table", "order_no", "STRING", "order_details.xlsx", "xlsx",
         json.dumps({"sheet": "Orders", "column": "C", "row_start": 3}), "Wide table order number"],
    ]
    edge_rows = [
        ["from_dataset", "from_field", "to_dataset", "to_field", "transform",
         "confidence", "note"],
        ["ods_raw", "order_no", "dwd_order", "", "", "", ""],   # only upstream field: reject
        ["ods_raw", "", "dwd_order", "order_no", "", "", ""],   # only downstream field: reject
        ["ods_raw", "", "dwd_order", "", "", "", ""],           # table-level edge: valid
        ["ods_raw", "order_no", "dwd_order", "order_no", "trim/cast", "1.0", ""],
    ]
    r = _import_csv(client, headers, ds_rows, edge_rows)
    assert r.status_code == 201, r.text
    report = r.json()["report"]
    assert report["summary"] == {"total": 6, "ok": 4, "merged": 0, "rejected": 2}
    rejected = [i for i in report["items"] if i["status"] == "rejected"]
    for item in rejected:
        assert item["kind"] == "edge"
        assert item["reason"] == "An edge must provide both upstream and downstream fields (field-level) or neither (table-level)"

    conn = _db()
    n_mixed = conn.execute(
        "SELECT COUNT(*) FROM edge WHERE (from_field IS NULL) != (to_field IS NULL)"
    ).fetchone()[0]
    n_table = conn.execute(
        "SELECT COUNT(*) FROM edge WHERE from_field IS NULL AND to_field IS NULL"
    ).fetchone()[0]
    conn.close()
    assert n_mixed == 0
    assert n_table == 1


# ---------- R3: batch rollback hitting a foreign-key reference → 409 ----------

def test_r3_rollback_blocked_by_later_batch_fk(client):
    headers = login(client)
    _seed_sources(client, headers)

    # batch1: create two ods_user fields
    r1 = _import_json(client, headers, {**_ods_user_manifest(), "lineage": []})
    assert r1.status_code == 201, r1.text
    batch1 = r1.json()["batch_id"]

    # batch2: an edge references a field added by batch1
    manifest2 = {
        "datasets": [],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_name",
             "to_dataset": "ods_user", "to_field": "user_id", "transform": "lookup"},
        ],
    }
    r2 = _import_json(client, headers, manifest2)
    assert r2.status_code == 201, r2.text
    batch2 = r2.json()["batch_id"]

    # Roll back batch1 directly: its fields are referenced by a batch2 edge → 409
    r = client.post(f"/import/batches/{batch1}/rollback", headers=headers)
    assert r.status_code == 409, r.text
    assert "roll back the later batch first" in r.json()["detail"]

    # Roll back batch2 first (deletes the edge), then batch1 → both succeed, the DB is clean
    assert client.post(f"/import/batches/{batch2}/rollback",
                       headers=headers).status_code == 200
    assert client.post(f"/import/batches/{batch1}/rollback",
                       headers=headers).status_code == 200
    snap = client.get("/lineage/snapshot", headers=headers).json()
    assert snap["fields"] == []
    assert snap["datasets"] == []


# ---------- R4: role changes take effect immediately ----------

def test_r4_role_change_takes_effect_immediately(client):
    admin_headers = login(client)
    editor_headers = create_user(client, admin_headers, "editor_user", "editor")
    # Before the downgrade the editor can upload
    upload(client, editor_headers, [("users.csv", user_csv_bytes(), "text/csv")])

    # M1 has no role-change endpoint; change the DB directly to simulate an admin downgrading editor_user to viewer
    conn = _db()
    conn.execute("UPDATE user SET role='viewer' WHERE username='editor_user'")
    conn.commit()
    conn.close()

    # An old token (still claiming editor in the JWT) uploads again → the DB role wins, 403
    r = client.post("/files", headers=editor_headers,
                    files=[("files", ("x.csv", b"a,b\n1,2\n", "text/csv"))])
    assert r.status_code == 403, r.text


# ---------- R5: manifest row-level parse errors reject only that row ----------

def test_r5_row_parse_error_rejects_row_not_batch(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = {
        "datasets": [
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_id",
             "field_type": "INTEGER", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"header": "user_id"}},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "bad_loc",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": "not-json"},
            {"dataset_id": "ods_user", "dataset_name": "Users", "field_name": "user_name",
             "field_type": "STRING", "src_file": "users.csv", "src_type": "csv",
             "src_locator": {"column": 2}},
        ],
        "lineage": [
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name",
             "transform": "lookup", "confidence": "abc"},
            {"from_dataset": "ods_user", "from_field": "user_id",
             "to_dataset": "ods_user", "to_field": "user_name",
             "transform": "lookup2", "confidence": "1.0"},
        ],
    }
    r = _import_json(client, headers, manifest)
    assert r.status_code == 201, r.text  # row-level errors do not reject the whole batch with 400
    report = r.json()["report"]
    assert report["summary"] == {"total": 5, "ok": 3, "merged": 0, "rejected": 2}
    bad_loc = next(i for i in report["items"] if i["ref"] == "ods_user.bad_loc")
    assert bad_loc["status"] == "rejected" and "src_locator" in bad_loc["reason"]
    bad_edge = next(i for i in report["items"]
                    if i["kind"] == "edge" and i["status"] == "rejected")
    assert "confidence" in bad_edge["reason"]

    # Valid rows are persisted normally
    ods = client.get("/datasets/ods_user", headers=headers).json()
    assert [f["name"] for f in ods["fields"]] == ["user_id", "user_name"]


# ---------- R6: same-pair merging / re-import idempotency ----------

def test_r6_same_pair_different_transform_merged(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = _ods_user_manifest()
    manifest["lineage"] = [
        {"from_dataset": "ods_user", "from_field": "user_id",
         "to_dataset": "ods_user", "to_field": "user_name", "transform": "t1"},
        {"from_dataset": "ods_user", "from_field": "user_id",
         "to_dataset": "ods_user", "to_field": "user_name", "transform": "t2"},
    ]
    r = _import_json(client, headers, manifest)
    assert r.status_code == 201, r.text
    assert r.json()["report"]["summary"]["merged"] == 1

    conn = _db()
    row = conn.execute(
        "SELECT transform FROM edge WHERE from_dataset='ods_user'"
        " AND from_field='user_id' AND to_dataset='ods_user' AND to_field='user_name'"
    ).fetchone()
    conn.close()
    assert row[0] == "t2"  # the DB holds the later value


def test_r6_reimport_idempotent_no_change_log(client):
    headers = login(client)
    _seed_sources(client, headers)
    manifest = _ods_user_manifest()

    r1 = _import_json(client, headers, manifest)
    assert r1.status_code == 201, r1.text
    conn = _db()
    before = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    conn.close()

    r2 = _import_json(client, headers, manifest)
    assert r2.status_code == 201, r2.text
    report2 = r2.json()["report"]
    assert report2["items"]  # non-empty and all ok + unchanged
    assert all(i["status"] == "ok" and i["reason"] == "unchanged"
               for i in report2["items"])

    conn = _db()
    after = conn.execute("SELECT COUNT(*) FROM change_log").fetchone()[0]
    conn.close()
    assert after == before  # the second import added no change_log entries


# ---------- R7: upload hardening ----------

def test_r7_upload_empty_file_list_400(client):
    headers = login(client)
    r = client.post("/files", headers=headers)
    assert r.status_code == 400, r.text
    assert "Upload at least one file" in r.json()["detail"]


def test_r7_upload_oversize_413(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    headers = login(client)
    big = b"a,b\n" + b"1,2\n" * 300_000  # ≈1.4MB, above the 1MB limit
    r = client.post("/files", headers=headers,
                    files=[("files", ("big.csv", big, "text/csv"))])
    assert r.status_code == 413, r.text
