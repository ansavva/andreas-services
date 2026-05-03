plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.47.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Modules inherit version constraints from root envs — don't require them in every module.
rule "terraform_required_version" {
  enabled = false
}

rule "terraform_required_providers" {
  enabled = false
}

# Tags are intentionally inconsistent across services — skip tag enforcement.
rule "aws_resource_missing_tags" {
  enabled = false
}
