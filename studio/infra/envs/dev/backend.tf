# The bucket is fixed; the KEY is not, and cannot be. Every machine has its own
# state, so the key carries the account and the machine UUID:
#
#   studio/dev/<account-id>/<machine-id>/terraform.tfstate
#
# `dev-aws-common.sh` computes that as STATE_KEY and passes it as
# `-backend-config="key=$STATE_KEY"` at init time. A hard-coded key here would
# have two machines silently sharing — and destroying — one state.
terraform {
  backend "s3" {
    bucket  = "andreas-services-terraform-state"
    region  = "us-east-1"
    encrypt = true
  }
}
