# Optional Amazon RDS PostgreSQL — production persistence outside the Compose host.
# When var.rds_enabled is false, no RDS resources are created (default for ephemeral stacks and local TF).

resource "random_password" "rds_master" {
  count  = var.rds_enabled && var.rds_master_password == "" ? 1 : 0
  length = 32
  # RDS rejects some punctuation; keep URL-safe for DATABASE_URL on EC2.
  special = false
}

locals {
  rds_master_password_effective = var.rds_enabled ? (
    var.rds_master_password != "" ? var.rds_master_password : random_password.rds_master[0].result
  ) : ""
}

resource "aws_db_subnet_group" "cns" {
  count      = var.rds_enabled ? 1 : 0
  name       = "${local.name_prefix}-rds-subnets"
  subnet_ids = [aws_subnet.public.id, aws_subnet.public_b.id]

  tags = {
    Name = "${local.name_prefix}-rds-subnets"
  }
}

resource "aws_security_group" "rds" {
  count       = var.rds_enabled ? 1 : 0
  name        = "${local.name_prefix}-rds-sg"
  description = "RDS PostgreSQL for Cloud Networking Studio (ingress from EC2 compose SG only)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from EC2 Compose host"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.instance.id]
  }

  egress {
    description      = "All outbound"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "${local.name_prefix}-rds-sg"
  }
}

resource "aws_db_instance" "cns" {
  count = var.rds_enabled ? 1 : 0

  identifier                 = "${local.name_prefix}-pg"
  engine                     = "postgres"
  engine_version             = "16"
  instance_class             = var.rds_instance_class
  allocated_storage          = var.rds_allocated_storage
  storage_type               = "gp3"
  db_name                    = var.rds_database_name
  username                   = var.rds_master_username
  password                   = local.rds_master_password_effective
  db_subnet_group_name       = aws_db_subnet_group.cns[0].name
  vpc_security_group_ids     = [aws_security_group.rds[0].id]
  publicly_accessible        = var.rds_publicly_accessible
  multi_az                   = false
  skip_final_snapshot        = true
  deletion_protection        = var.rds_deletion_protection
  backup_retention_period    = var.rds_backup_retention_period
  auto_minor_version_upgrade = true

  tags = {
    Name = "${local.name_prefix}-rds"
  }
}
