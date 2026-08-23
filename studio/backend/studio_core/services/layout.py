"""The folder layout every entity starts with — convention, and nothing else.

**An entity record holds exactly one node id: `root`** (a run, scene or movie
calls it `folder`). It does not enumerate `reference/`, `corpus/`, `runs/` or
`input/`, and there is no `folders` map anywhere in the table.

An earlier draft of the entity model put a five-key map on each record. It was
wrong on three counts, and the third is the one that keeps mattering:

1. **It is derived state.** The folders are children of `root` and one
   `GetItem` on `NODE#<root>` / `NAME#reference` finds any of them. Storing the
   ids caches a lookup that costs a single read.
2. **It goes stale, and the file layer is what breaks it.** A person can rename
   `reference/`, move it or delete it — those are ordinary file operations and
   they must stay ordinary. A stored map would then name a folder with a
   different name, a different parent, or no existence.
3. **It is rigid where the product is not.** People make their own folders. A
   model enumerating five blessed ones implies the other twelve are
   second-class, and they are not.

**What replaced the map is that pools stopped being structural.** `reference/`
used to be load-bearing because reference-ness was *inferred from the path*. It
is a `CHAR#<id>` / `REF#<node>` row now, so an image is identity because a row
says so and **not because of which folder it sits in**. `corpus/`, `seed/` and
`archive/` were never anything but folders with conventions attached, and they
are now exactly that.

## Resolution is by name, at write time, and self-healing

`POST /api/runs` asks for `runs` under the project's root and **creates it if it
is absent**. If somebody renamed `runs/` last week a new one appears, and every
existing run stays perfectly reachable — a run record names its own folder node
id rather than a path. Same for scenes, movies and the input pool. A route that
cannot find its conventional folder makes one; it never fails, and it never
guesses.

`folder_under` is therefore deliberately not a read followed by a create: it
tries the read, and turns the miss into a create whose own conflict is read
again. Two callers resolving `runs/` at the same instant produce one folder and
two winners, because the loser of the conditional put re-reads what the winner
wrote.

## The one hard rule this leaves

**A folder that is some entity's `root` cannot be deleted while the entity
exists.** `DELETE /api/nodes` refuses it and says which entity to delete
instead. That refusal lives in `services.catalog`, next to the `entity`
attribute it reads, because it is a property of the row rather than of the
convention here.
"""

from studio_core.errors import ConflictError, NotFoundError
from studio_core.services import catalog

# What a character is created holding. Four folders, because an empty character
# is unhelpful — not because anything afterwards requires them.
CHARACTER_LAYOUT = ("reference", "corpus", "seed", "archive")

# What a project is created holding. `chains/` is an ad-hoc frame sequence with
# no scene behind it, and is deliberately an ordinary folder rather than a sixth
# entity type.
PROJECT_LAYOUT = ("runs", "scenes", "movies", "chains", "input")

# Where each project-scoped entity puts its own folder, and where the working
# pool is read from. Named separately from the tuple above rather than indexed
# out of it: a person may delete `chains/` and nothing breaks, while these four
# are the names four routes ask for by name, and an index would silently follow
# a reordering of the layout.
RUN_PARENT = "runs"
SCENE_PARENT = "scenes"
MOVIE_PARENT = "movies"
INPUT_FOLDER = "input"

# The run's own output pool, made with the run so that `POST /api/runs/<id>/
# outputs` has somewhere to land without resolving anything.
OUTPUT_FOLDER = "output"

# Shared material that belongs to the library rather than to any entity: the
# pose plates. It is a folder of ordinary nodes, pushed through `POST /api/nodes`
# by `scripts/dev-setup.sh` and by the deploy, with the repo as its source of
# truth. Before the entity model these plates had no node at all, which is the
# whole reason `GET /api/asset?key=` took a raw S3 key; giving them one is what
# retired it.
CONFIG_FOLDER = "config"


def folder_under(parent_id: str, name: str) -> dict:
    """The folder called `name` under `parent_id`, made if it is not there.

    **Read, then conditional create, then read again**, and the third step is
    the one worth keeping. `catalog.create_node` puts its `NAME#` item under
    `attribute_not_exists(pk)`, so two requests resolving `runs/` at the same
    moment produce exactly one folder — and the loser sees a `ConflictError`
    that means "somebody else made it", which is success rather than failure.
    Re-reading is how it learns the winner's node id.

    A *file* already called `runs` is a different matter and is not swallowed:
    `catalog.create_node`'s conflict is re-read, the read hands back a file, and
    the caller is told rather than being given somewhere it cannot write.
    """
    try:
        return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])
    except NotFoundError:
        pass

    try:
        return catalog.create_node(parent_id, name, catalog.KIND_FOLDER)
    except ConflictError:
        # Lost the race. Whatever is there now is what both callers get.
        return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])
