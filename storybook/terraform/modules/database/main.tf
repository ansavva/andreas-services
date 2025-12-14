# modules/database/main.tf
# DocumentDB cluster for production environment

# Security group for DocumentDB
resource "aws_security_group" "docdb" {
  name        = "${var.project}-docdb-${var.environment}"
  description = "Security group for DocumentDB cluster"
  vpc_id      = var.vpc_id

  ingress {
    description = "MongoDB port from Lambda"
    from_port   = 27017
    to_port     = 27017
    protocol    = "tcp"
    security_groups = var.lambda_security_group_ids
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project}-docdb-${var.environment}"
  })
}

# Subnet group for DocumentDB
resource "aws_docdb_subnet_group" "main" {
  name       = "${var.project}-docdb-subnet-${var.environment}"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.project}-docdb-subnet-${var.environment}"
  })
}

# DocumentDB cluster parameter group
resource "aws_docdb_cluster_parameter_group" "main" {
  family      = "docdb5.0"
  name        = "${var.project}-docdb-params-${var.environment}"
  description = "DocumentDB cluster parameter group for ${var.project}"

  parameter {
    name  = "tls"
    value = "enabled"
  }

  tags = var.tags
}

# DocumentDB cluster
resource "aws_docdb_cluster" "main" {
  cluster_identifier              = "${var.project}-docdb-${var.environment}"
  engine                          = "docdb"
  engine_version                  = "5.0.0"
  master_username                 = var.master_username
  master_password                 = var.master_password
  db_subnet_group_name            = aws_docdb_subnet_group.main.name
  db_cluster_parameter_group_name = aws_docdb_cluster_parameter_group.main.name
  vpc_security_group_ids          = [aws_security_group.docdb.id]

  backup_retention_period      = var.backup_retention_days
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"

  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.project}-docdb-final-${var.environment}-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  enabled_cloudwatch_logs_exports = ["audit", "profiler"]

  storage_encrypted = true
  kms_key_id        = var.kms_key_id

  tags = merge(var.tags, {
    Name = "${var.project}-docdb-${var.environment}"
  })
}

# DocumentDB cluster instances
resource "aws_docdb_cluster_instance" "main" {
  count              = var.instance_count
  identifier         = "${var.project}-docdb-${var.environment}-${count.index + 1}"
  cluster_identifier = aws_docdb_cluster.main.id
  instance_class     = var.instance_class

  tags = merge(var.tags, {
    Name = "${var.project}-docdb-${var.environment}-${count.index + 1}"
  })
}
