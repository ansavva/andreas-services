"""`studio catalog` — the bucket recorded as rows, without a byte moving.

The three phases are checked against each other rather than against a golden
file: `plan` derives the tree, `seed` writes it, and `verify` reads the table
back and re-lists the bucket. What is worth testing here is the properties the
phases rely on and a report cannot show — that a node is two items and the root
is one, that the plan is reproducible so a resumed seed recognises its own work,
that `created_at` orders a shared second, and that `verify` actually fails when
the bucket and the table disagree.

The moto bucket is the shared miniature from `conftest.py`; the catalog table is
built here with the three GSIs the schema calls for, because an index silently
drops any row missing one of its key attributes — which is exactly the kind of
bug a table with no indexes would hide.
"""

import datetime as dt

from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.maintenance import catalog_seed as cs

# The shape of a Cognito `sub`, and nothing more — the command takes it as a
# required option precisely so nothing has to guess or look one up.
OWNER_SUB = "11111111-2222-3333-4444-555555555555"

def _seed(s3, ddb, **over):
    plan = cs.build_plan(s3)
    args = {"owner_sub": OWNER_SUB, "library_name": "Studio", "apply": True}
    return plan, cs.phase_seed(ddb, plan, **{**args, **over})


def _get(ddb, pk, sk):
    got = ddb.get_item(TableName=ddbc.TABLE, Key={"pk": {"S": pk}, "sk": {"S": sk}})
    return ddbc.from_item(got["Item"]) if "Item" in got else None


# ── the plan ────────────────────────────────────────────────────────────────

def test_the_root_is_a_real_row_with_no_parent_and_no_name(media_bucket):
    """The absent `parent_id` is what makes rename/move/delete of the root refuse."""
    plan = cs.build_plan(media_bucket)
    root = plan["nodes"][0]
    assert root["node_id"] == plan["root"]
    assert root["parent_id"] is None
    assert root["path"] == "/"
    assert root["kind"] == "folder"

    item = cs.meta_item(root)
    assert item["pk"] == f"NODE#{plan['root']}" and item["sk"] == "META"
    # Absent, not null: an absent attribute is what `attribute_not_exists` tests.
    assert "parent_id" not in item and "name" not in item


def test_every_object_becomes_one_file_node_holding_the_key_that_exists(media_bucket):
    plan = cs.build_plan(media_bucket)
    claimed = [n["blob_key"] for n in plan["nodes"] if n["kind"] == "file"]
    listed = {obj["Key"]
              for obj in media_bucket.list_objects_v2(Bucket=s3c.BUCKET)["Contents"]
              if not obj["Key"].startswith(cs.SHARED_PREFIXES)}
    assert sorted(claimed) == sorted(listed)
    assert len(claimed) == len(set(claimed))


def test_every_intermediate_prefix_becomes_a_folder(media_bucket):
    """Walking a file node's parents back to the root spells its key."""
    plan = cs.build_plan(media_bucket)
    by_id = {n["node_id"]: n for n in plan["nodes"]}
    key = ("projects/subject-a/runs/2026-08-04_21-30-54_wave-porch"
           "/output/wave-porch.jpeg")

    node = next(n for n in plan["nodes"] if n.get("blob_key") == key)
    names = []
    while node["parent_id"] is not None:
        names.append(node["name"])
        node = by_id[node["parent_id"]]
    assert list(reversed(names)) == key.split("/")
    assert node["node_id"] == plan["root"]


def test_path_is_the_materialised_ancestor_ids(media_bucket):
    plan = cs.build_plan(media_bucket)
    by_id = {n["node_id"]: n for n in plan["nodes"]}
    for node in plan["nodes"][1:]:
        parent = by_id[node["parent_id"]]
        assert node["path"] == parent["path"] + parent["node_id"] + "/"


def test_shared_prefixes_belong_to_no_library(shared_objects):
    plan = cs.build_plan(shared_objects)
    assert len(plan["shared"]) == 3          # two pose plates + the phrasebook
    assert not [n for n in plan["nodes"]
                if (n.get("blob_key") or "").startswith(cs.SHARED_PREFIXES)]
    # Not even the top-level folder: a prefix nothing records is not a node.
    assert not [n for n in plan["nodes"] if n["name"] in ("config", "phrasebook")]


def test_a_folder_marker_is_a_folder_node_and_never_a_file(media_bucket):
    media_bucket.put_object(Bucket=s3c.BUCKET, Key="projects/subject-a/empty/", Body=b"")
    plan = cs.build_plan(media_bucket)

    assert plan["markers"] == ["projects/subject-a/empty/"]
    node = next(n for n in plan["nodes"] if n["name"] == "empty")
    assert node["kind"] == "folder"
    assert "blob_key" not in node


def test_a_key_that_is_both_a_file_and_a_folder_is_unmapped(media_bucket):
    """Two nodes cannot share a name in one folder — that is the index item."""
    media_bucket.put_object(Bucket=s3c.BUCKET,
                            Key="projects/subject-a/project.json/extra", Body=b"x")
    plan = cs.build_plan(media_bucket)

    assert len(plan["unmapped"]) == 1
    assert "project.json" in plan["unmapped"][0]


def test_the_plan_is_a_pure_function_of_the_bucket(media_bucket):
    """The property a resumed seed depends on: same bucket, same ids and stamps."""
    assert cs.build_plan(media_bucket) == cs.build_plan(media_bucket)


# ── created_at ──────────────────────────────────────────────────────────────

def test_created_at_resolves_a_shared_second_on_the_key():
    """The tie-break `_sort_files` still does at read time, done once at write.

    Note the ordering is on the whole key and lexical, not natural — `b/10.png`
    before `b/2.png` — because that is what the reel does today and the point is
    to reproduce it, not to improve on it here.
    """
    second = dt.datetime(2026, 8, 4, 21, 30, 54, tzinfo=dt.timezone.utc)
    files = [("b/2.png", second, 1), ("b/10.png", second, 1),
             ("a/1.png", second, 1),
             ("z/0.png", second + dt.timedelta(seconds=1), 1)]

    stamps = cs.created_stamps(files)
    assert sorted(stamps, key=stamps.get) == ["a/1.png", "b/10.png", "b/2.png",
                                              "z/0.png"]
    assert stamps["a/1.png"] == "2026-08-04T21:30:54.000000+00:00"
    assert stamps["b/10.png"] == "2026-08-04T21:30:54.000001+00:00"
    assert stamps["z/0.png"] == "2026-08-04T21:30:55.000000+00:00"


def test_every_file_node_gets_a_distinct_created_at(media_bucket):
    """Distinct is what retires the tie-break; a `by-recent` page depends on it."""
    files = [n for n in cs.build_plan(media_bucket)["nodes"] if n["kind"] == "file"]
    assert len({n["created_at"] for n in files}) == len(files)


def test_a_folder_is_as_old_as_the_oldest_thing_under_it(media_bucket):
    plan = cs.build_plan(media_bucket)
    by_id = {n["node_id"]: n for n in plan["nodes"]}
    children = {}
    for node in plan["nodes"][1:]:
        children.setdefault(node["parent_id"], []).append(node["created_at"])
    for parent_id, stamps in children.items():
        if by_id[parent_id]["parent_id"] is None:
            continue                     # the root predates its content by fiat
        assert by_id[parent_id]["created_at"] == min(stamps)


# ── seed ────────────────────────────────────────────────────────────────────

def test_seed_creates_the_library_its_owner_and_its_root(media_bucket, catalog_table):
    plan, res = _seed(media_bucket, catalog_table)
    assert res["library_created"]

    library = _get(catalog_table, f"LIB#{plan['lib']}", "META")
    assert library["root_node"] == plan["root"]
    assert library["name"] == "Studio"

    membership = _get(catalog_table, f"USER#{OWNER_SUB}", f"LIB#{plan['lib']}")
    assert membership["role"] == "owner"

    root = _get(catalog_table, f"NODE#{plan['root']}", "META")
    assert root is not None and "parent_id" not in root


def test_a_node_is_two_items_and_the_root_is_one(media_bucket, catalog_table):
    plan, _ = _seed(media_bucket, catalog_table)
    items = list(ddbc.scan(catalog_table))
    # library + membership + META for every node + NAME# for every node but the root
    assert len(items) == 2 + len(plan["nodes"]) + (len(plan["nodes"]) - 1)


def test_the_by_parent_item_carries_no_mutable_file_metadata(media_bucket):
    """Widening this projection would put every rename in the metadata business."""
    plan = cs.build_plan(media_bucket)
    node = next(n for n in plan["nodes"] if n["kind"] == "file")

    item = cs.index_item(node)
    assert set(item) == {"pk", "sk", "node_id", "lib", "kind", "path", "created_at"}
    assert item["sk"] == f"NAME#{node['name']}"
    assert item["pk"] == f"NODE#{node['parent_id']}"


def test_a_file_node_records_size_and_content_type(media_bucket, catalog_table):
    plan, _ = _seed(media_bucket, catalog_table)
    key = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch/output/wave-porch.jpeg"
    node = next(n for n in plan["nodes"] if n.get("blob_key") == key)

    stored = _get(catalog_table, f"NODE#{node['node_id']}", "META")
    assert stored["blob_key"] == key            # the key that already exists
    assert stored["size"] == len(b"jpeg-bytes")
    assert stored["content_type"] == "image/jpeg"
    assert stored["updated_at"] == stored["created_at"]


def test_a_dry_run_writes_nothing(media_bucket, catalog_table):
    plan, res = _seed(media_bucket, catalog_table, apply=False)
    assert len(res["created"]) == len(plan["nodes"]) - 1
    assert list(ddbc.scan(catalog_table)) == []


def test_a_second_seed_creates_nothing(media_bucket, catalog_table):
    """An interrupted seed is resumable, which is the whole reason ids are derived."""
    _seed(media_bucket, catalog_table)
    before = len(list(ddbc.scan(catalog_table)))

    plan, res = _seed(media_bucket, catalog_table)
    assert res["created"] == []
    assert res["library_created"] is False
    assert len(res["skipped"]) == len(plan["nodes"]) - 1
    assert len(list(ddbc.scan(catalog_table))) == before


def test_every_node_is_reachable_through_the_by_path_index(media_bucket, catalog_table):
    """A subtree listing is a `begins_with` — and an index drops a row missing a key."""
    plan, _ = _seed(media_bucket, catalog_table)
    page = catalog_table.query(
        TableName=ddbc.TABLE, IndexName="by-path",
        KeyConditionExpression="#l = :lib AND begins_with(#p, :root)",
        ExpressionAttributeNames={"#l": "lib", "#p": "path"},
        ExpressionAttributeValues={":lib": {"S": plan["lib"]},
                                   ":root": {"S": "/" + plan["root"] + "/"}},
    )
    found = {ddbc.from_item(item)["node_id"] for item in page["Items"]}
    assert found == {n["node_id"] for n in plan["nodes"][1:]}


# ── verify ──────────────────────────────────────────────────────────────────

def test_verify_passes_on_a_freshly_seeded_bucket(shared_objects, catalog_table):
    plan, _ = _seed(shared_objects, catalog_table)
    res = cs.phase_verify(shared_objects, catalog_table, plan)

    assert res["ok"], res["problems"]
    assert res["claimed"] == res["objects"]
    assert res["shared"] == 3
    assert res["members"] == 1


def test_a_shared_object_is_not_an_orphan(shared_objects, catalog_table):
    """`config/` and `phrasebook/` are unclaimed on purpose, not by omission."""
    plan, _ = _seed(shared_objects, catalog_table)
    shared_objects.put_object(Bucket=s3c.BUCKET,
                              Key="config/pose/body/seated.png", Body=b"png-bytes")

    res = cs.phase_verify(shared_objects, catalog_table, plan)
    assert res["ok"], res["problems"]
    assert res["shared"] == 4


def test_verify_reports_an_object_no_node_claims(media_bucket, catalog_table):
    plan, _ = _seed(media_bucket, catalog_table)
    media_bucket.put_object(Bucket=s3c.BUCKET,
                            Key="projects/subject-a/input/subject-a_4.png",
                            Body=b"png-bytes")

    res = cs.phase_verify(media_bucket, catalog_table, plan)
    assert not res["ok"]
    assert res["problems"]["unclaimed"] == ["projects/subject-a/input/subject-a_4.png"]


def test_verify_reports_a_node_whose_blob_is_gone(media_bucket, catalog_table):
    plan, _ = _seed(media_bucket, catalog_table)
    key = "projects/subject-a/input/subject-a_1.webp"
    media_bucket.delete_object(Bucket=s3c.BUCKET, Key=key)

    res = cs.phase_verify(media_bucket, catalog_table, plan)
    assert not res["ok"]
    assert [p for p in res["problems"]["missing_blob"] if p.endswith(key)]


def test_verify_reports_a_node_missing_its_by_parent_item(media_bucket, catalog_table):
    """A node with no index item is invisible to a folder listing and fine by id."""
    plan, _ = _seed(media_bucket, catalog_table)
    node = next(n for n in plan["nodes"] if n["kind"] == "file")
    catalog_table.delete_item(
        TableName=ddbc.TABLE,
        Key={"pk": {"S": f"NODE#{node['parent_id']}"},
             "sk": {"S": f"NAME#{node['name']}"}})

    res = cs.phase_verify(media_bucket, catalog_table, plan)
    assert not res["ok"]
    assert res["problems"]["no_index_item"] == [node["node_id"]]


def test_verify_fails_against_an_unseeded_table(media_bucket, catalog_table):
    """The check has to be able to fail, or passing means nothing."""
    plan = cs.build_plan(media_bucket)
    res = cs.phase_verify(media_bucket, catalog_table, plan)

    assert not res["ok"]
    assert res["problems"]["no_library"]
    assert len(res["problems"]["unclaimed"]) == res["objects"]


# ── the CLI ─────────────────────────────────────────────────────────────────

def test_plan_runs_from_the_cli(media_bucket, tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "JOURNAL_DIR", str(tmp_path))
    result = CliRunner().invoke(cli.main, ["catalog", "plan"])

    assert result.exit_code == 0, result.output
    assert "library    lib-" in result.output
    assert "UNMAPPED" in result.output
    assert (tmp_path / result.output.rsplit("journal: ", 1)[1].strip().rsplit("/", 1)[1]
            ).is_file()


def test_seed_refuses_without_an_owner_sub(media_bucket, tmp_path, monkeypatch):
    """The Cognito `sub` is asked for, never looked up or guessed."""
    monkeypatch.setattr(cs, "JOURNAL_DIR", str(tmp_path))
    result = CliRunner().invoke(cli.main, ["catalog", "seed", "--apply"])

    assert result.exit_code == 2
    assert "--owner-sub" in result.output


def test_seed_refuses_when_the_table_does_not_exist(media_bucket, tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "JOURNAL_DIR", str(tmp_path))
    result = CliRunner().invoke(
        cli.main, ["catalog", "seed", "--owner-sub", OWNER_SUB])

    assert result.exit_code == 1
    assert ddbc.TABLE in result.output


def test_seed_and_verify_run_from_the_cli(shared_objects, catalog_table, tmp_path,
                                          monkeypatch):
    monkeypatch.setattr(cs, "JOURNAL_DIR", str(tmp_path))
    runner = CliRunner()

    seeded = runner.invoke(cli.main, ["catalog", "seed", "--owner-sub", OWNER_SUB,
                                      "--apply"])
    assert seeded.exit_code == 0, seeded.output

    verified = runner.invoke(cli.main, ["catalog", "verify"])
    assert verified.exit_code == 0, verified.output
    assert "VERIFY: PASS" in verified.output
