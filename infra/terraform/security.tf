resource "aws_security_group" "instance" {
  name        = "${local.name_prefix}-sg"
  description = "Cloud Networking Studio Compose host"
  vpc_id      = aws_vpc.main.id

  # SSH: single ingress rule driven by var.ssh_allowed_cidr (e.g. MY_IP/32 for admin, 0.0.0.0/0 only when required for CI — see docs).
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
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
    Name = "${local.name_prefix}-sg"
  }
}
