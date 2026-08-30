terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # The major `envs/dev` and `envs/prod` both pin, so a standalone
      # `terraform validate` here sees the provider the environments use.
      version = ">= 6.12, < 7.0"
    }
    # **Declared rather than left to auto-install**, because this module is the
    # only thing in studio that packages code: the receiver is a zip built from
    # `backend/` at plan time. An undeclared provider resolves anyway and then
    # silently floats across major versions, and this one decides the bytes that
    # reach a public endpoint.
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4, < 3.0"
    }
  }
}
