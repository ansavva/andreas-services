variable "name_prefix" {
  description = <<-EOT
    Everything here is named `<prefix>-render…`. Prod passes `studio-prod`, so
    the queue is `studio-prod-render` and its dead-letter queue
    `studio-prod-render-dlq`; dev passes `studio-dev-<short12>`, because the
    machine id is inside the environment segment there and two developers share
    one account.

    A prefix rather than the `project` + `environment` pair the other modules
    take, for the reason `modules/callbacks` gives: the dev environment passes a
    compound value and this module should have no opinion about what an
    environment is called.
  EOT
  type        = string
}

variable "create_ecr" {
  description = <<-EOT
    Whether this environment gets an image repository. **A literal, never derived
    from a resource attribute** — it drives a `count`, and a count that depends
    on one cannot be resolved at plan time.

    `false` is what the per-machine dev environment passes: it builds no images,
    and its queue is drained by a process beside `dev-up.sh` running the
    developer's own working tree against the ffmpeg in their own virtualenv.
  EOT
  type        = bool
  default     = false
}

variable "create_worker" {
  description = <<-EOT
    Whether this environment gets a queue consumer Lambda. Same rule and same
    reason as `create_ecr`, and the two are set together in practice — there is
    no worker without an image for it to run.
  EOT
  type        = bool
  default     = false
}

variable "worker_image_uri" {
  description = <<-EOT
    The render image, which is **not** the API's. `Dockerfile.render` is the API's
    Dockerfile plus one Poetry group (`imageio-ffmpeg`) and a different `CMD`, so
    the two cannot drift in application code — but it is a separate build, a
    separate repository and a separate ~80 MB that no folder listing pays for.

    Required when `create_worker` is true; ignored otherwise.
  EOT
  type        = string
  default     = ""
}

variable "create_api_grant" {
  description = <<-EOT
    Whether the API Lambda's role gets `sqs:SendMessage` on this queue. **A
    literal**, for the reason `create_ecr` gives — it drives a `count`, and the
    obvious alternative (`api_role_name != ""`) would put a resource attribute
    inside one.

    `false` is what the per-machine dev environment passes: the API there is a
    process under a developer's own IAM key, not a Lambda with a role to attach
    anything to.
  EOT
  type        = bool
  default     = false
}

variable "api_role_name" {
  description = <<-EOT
    The API Lambda's execution role, so the `sqs:SendMessage` grant can be
    attached to it as an inline policy. Empty skips the grant, which is what an
    environment with no API Lambda — the per-machine dev stack, where the API is
    a process under a developer's own key — passes.
  EOT
  type        = string
  default     = ""
}

variable "media_access_policy" {
  description = <<-EOT
    `modules/compute`'s media-bucket policy document, attached here to the
    worker's OWN role.

    A document rather than the role itself, and that is the difference from
    `modules/callbacks`. That worker does what the API does, provider token
    included, so it takes the API's role whole. This one never calls Replicate —
    it joins files that are already in the library — so taking the API's role
    would hand it the ability to spend money for no code path that spends any.
    Sharing the document keeps one definition of what library access means;
    separate roles keep each function scoped to its job.

    Empty means no policy is attached, which is only correct where no worker is
    created.
  EOT
  type        = string
  default     = ""
}

variable "catalog_access_policy" {
  description = "`modules/compute`'s catalog-table policy document. Same argument as `media_access_policy`."
  type        = string
  default     = ""
}

variable "media_bucket_name" {
  description = "Media bucket the worker reads inputs from and writes cuts into."
  type        = string
  default     = ""
}

variable "catalog_table_name" {
  description = "Catalog table the worker reads nodes from and records cuts in."
  type        = string
  default     = ""
}

variable "worker_timeout" {
  description = <<-EOT
    Wall clock for one render, in seconds. Ten minutes: **well under the
    fifteen-minute Lambda ceiling on purpose**, so that a job which is merely slow
    is killed with a timeout somebody can read rather than by the platform's hard
    limit, which arrives with no application log line at all.

    What it has to cover is the worst realistic cut — several 1080p clips
    downloaded, re-encoded with libx264 at `-crf 18 -preset medium`, and one
    `PutObject` back. A stream copy of the same material is seconds; the budget is
    for the case where the inputs disagree and ffmpeg has to normalise them.

    Also sets the queue's visibility timeout (this plus a minute), so raising it
    lengthens how long a failed message waits before it comes back.
  EOT
  type        = number
  default     = 600
}

variable "worker_memory" {
  description = <<-EOT
    Lambda's memory setting is also its CPU share, and **CPU is what this buys**.
    A re-encode is libx264, which is compute-bound and threaded; at 4 GB the
    function gets multiple vCPUs, and the difference between that and the 2 GB the
    callback worker runs at is minutes of wall clock on a long cut.

    It is not sized to the file. Clips are streamed to `/tmp` and ffmpeg reads
    them from there, so nothing large enters the heap — `ephemeral_storage` below
    is the one sized to the media.
  EOT
  type        = number
  default     = 4096
}

variable "worker_ephemeral_storage" {
  description = <<-EOT
    `/tmp`, in MB, and this IS sized to the media. The default 512 MB is not
    close: a movie is every scene downloaded plus the cut, so the peak is roughly
    **twice** the sum of the inputs, and a multi-clip 1080p cut passes 512 MB on
    its second shot.

    10 GB is the Lambda maximum and is what this takes, because the cost is
    per-invocation-millisecond on the amount *above* 512 MB rather than a
    standing charge — an idle render worker with 10 GB configured costs nothing.
    `media/workspace.reserve` measures the real free space before downloading
    anything and refuses the job with both numbers in the message, so the failure
    mode when this is still too small is a sentence rather than an `ENOSPC` from
    inside ffmpeg.
  EOT
  type        = number
  default     = 10240
}

variable "alarm_topic_arn" {
  description = <<-EOT
    SNS topic the dead-letter alarm publishes to. **Empty means the alarm still
    exists and notifies nobody** — it fires and is visible in the console. Studio
    has no notification convention yet and inventing a topic plus a subscription
    here would be a second feature riding along with this change; stated rather
    than hidden.
  EOT
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
