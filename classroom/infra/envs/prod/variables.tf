# No environment-specific inputs yet. Everything classroom needs is either
# derived in main.tf's locals or read from a shared data source; secrets would
# be declared here with `sensitive = true` and passed via TF_VAR_* in CI.
