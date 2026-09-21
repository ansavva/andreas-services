# One state for the whole team, unlike `envs/dev`, whose key carries a machine
# id. `use_lockfile` because two developers CAN run dev-aws-setup.sh at the
# same minute, and the per-machine stacks never needed a lock for that.
terraform {
  backend "s3" {
    bucket       = "andreas-services-terraform-state"
    key          = "humbugg/dev-shared/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
