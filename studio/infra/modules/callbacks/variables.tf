variable "name_prefix" {
  description = <<-EOT
    Everything here is named `<prefix>-callback…`. Prod passes
    `studio-prod`; dev passes `studio-dev-<short12>`, because the machine id is
    inside the environment segment there and two developers share one account.

    A prefix rather than the `project` + `environment` pair the other modules
    take, precisely so the dev environment can pass a compound value without
    this module having an opinion about what an environment is called.
  EOT
  type        = string
}

variable "media_bucket_name" {
  description = "Media bucket the worker stores outputs in. Prod only; unused when no worker is created."
  type        = string
  default     = ""
}

variable "catalog_table_name" {
  description = "Catalog table the worker closes runs in. Prod only."
  type        = string
  default     = ""
}

variable "replicate_token_parameter" {
  description = <<-EOT
    Name of the SSM SecureString holding the Replicate API token, reaching the
    worker as `STUDIO_REPLICATE_TOKEN_PARAMETER`. A NAME, never a value: the
    secret is read at call time by the execution role so it never sits in a
    function's environment, where `lambda:GetFunctionConfiguration` would hand it
    to anyone who can list the account.
  EOT
  type        = string
  default     = ""
}

variable "create_worker" {
  description = <<-EOT
    Whether this environment gets a queue consumer Lambda. **A literal, never
    derived from another resource**: it drives a `count`, and a `count` that
    depends on a resource attribute cannot be resolved at plan time — which
    failed a prod deploy in `modules/compute` and was latent here.

    `false` is what the per-machine dev environment passes: it has no ECR
    repository, and the queue is drained by a process beside `dev-up.sh` running
    the developer's own working tree.
  EOT
  type        = bool
  default     = false
}

variable "worker_image_uri" {
  description = <<-EOT
    The API's container image, which the worker runs at a different handler.
    **Empty means no worker is created**, which is what the per-machine dev
    environment passes: there is no ECR repository there, and the consumer is a
    process beside `dev-up.sh` that long-polls the queue with the developer's own
    working tree. That is the whole reason receive and process are separate
    functions — see main.tf.
  EOT
  type        = string
  default     = ""
}

variable "worker_role_arn" {
  description = <<-EOT
    Execution role for the worker. Pass the API Lambda's: the work is identical —
    the media bucket, the catalog, the provider token — and a second role would
    be a hand-maintained copy of the policies in `modules/compute` that drifts.
    Required when `worker_image_uri` is set.
  EOT
  type        = string
  default     = ""
}

variable "worker_role_name" {
  description = "Name of the same role, so the queue grant can be attached to it as an inline policy."
  type        = string
  default     = ""
}

variable "worker_timeout" {
  description = <<-EOT
    Wall clock for one batch of callbacks. It has to cover downloading a model
    output and putting it in the bucket, which for a 15-second video is tens of
    seconds of transfer — not the 60 the API Lambda runs with, which bounds a
    catalog transaction.

    Also sets the queue's visibility timeout (this plus a minute), so raising it
    lengthens how long a failed message waits before it comes back.
  EOT
  type        = number
  default     = 300
}

variable "worker_memory" {
  description = <<-EOT
    Lambda's memory setting is also its CPU and network share, which is what this
    is really buying: the download and the upload are the whole job. The output
    itself never enters the heap — it is streamed to `/tmp` — so this is not
    sized to the file.
  EOT
  type        = number
  default     = 2048
}

variable "worker_ephemeral_storage" {
  description = <<-EOT
    `/tmp`, in MB, and this one IS sized to the file: the output is streamed to
    disk and then sent as a single PutObject, so the whole of it has to fit.
    Single because a multipart upload's ETag is a hash of part hashes rather than
    the object's MD5, and every output would land with no checksum.
  EOT
  type        = number
  default     = 4096
}

variable "throttle_rate" {
  description = "Steady-state requests per second the public callback endpoint accepts."
  type        = number
  default     = 20
}

variable "throttle_burst" {
  description = "Burst above the steady rate the public callback endpoint accepts."
  type        = number
  default     = 40
}

variable "alarm_topic_arn" {
  description = <<-EOT
    SNS topic the dead-letter alarm publishes to. **Empty means the alarm still
    exists and notifies nobody** — it fires and is visible in the console, and
    that is deliberately called out rather than hidden: studio has no
    notification convention yet, and inventing a topic plus a subscription here
    would be a second feature riding along with the callback path.
  EOT
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to all resources"
  type        = map(string)
  default     = {}
}
