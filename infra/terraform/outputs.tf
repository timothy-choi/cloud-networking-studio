output "public_ip" {
  description = "Elastic IP attached to the Compose host."
  value       = aws_eip.cns.public_ip
}

output "security_group_id" {
  description = "Security group ID for the Compose host (SSH from ssh_allowed_cidr)."
  value       = aws_security_group.instance.id
}

output "subnet_id" {
  description = "Public subnet ID where the instance runs (routed to the VPC internet gateway)."
  value       = aws_subnet.public.id
}

output "vpc_id" {
  description = "VPC ID for the Compose stack."
  value       = aws_vpc.main.id
}

output "public_url" {
  description = "HTTP URL for the stack (same host as Caddy on port 80 after you deploy Compose)."
  value       = "http://${aws_eip.cns.public_ip}"
}

output "sslip_host" {
  description = "sslip.io hostname for this Elastic IP (resolves to public_ip)."
  value       = "${aws_eip.cns.public_ip}.sslip.io"
}

output "stack_base_url_sslip" {
  description = "HTTPS origin for the EC2 stack via sslip (production Caddy + Let's Encrypt; use stack_base_url_sslip_http for HTTP-only smoke)."
  value       = "https://${aws_eip.cns.public_ip}.sslip.io"
}

output "stack_base_url_sslip_http" {
  description = "HTTP origin for sslip (production + ephemeral smoke: CNS_BASE_URL; avoids HTTPS/TLS flakes on sslip.io)."
  value       = "http://${aws_eip.cns.public_ip}.sslip.io"
}

output "api_base_url_sslip" {
  description = "HTTPS API base for split Vercel UI (default VITE_API_BASE_URL in deploy-production when VERCEL_VITE_API_BASE_URL unset)."
  value       = "https://${aws_eip.cns.public_ip}.sslip.io/api"
}

output "api_base_url_sslip_http" {
  description = "HTTP API base for sslip (smoke scripts, debugging; same path shape as api_base_url_sslip)."
  value       = "http://${aws_eip.cns.public_ip}.sslip.io/api"
}

output "ssh_command" {
  description = "Example SSH command (default Ubuntu user)."
  value       = "ssh -i /path/to/${var.key_name}.pem ubuntu@${aws_eip.cns.public_ip}"
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.cns.id
}

# --- RDS (empty when var.rds_enabled is false; password is never output) ---

output "rds_address" {
  description = "RDS hostname for DATABASE_URL on EC2 (empty if RDS disabled)."
  value       = length(aws_db_instance.cns) > 0 ? aws_db_instance.cns[0].address : ""
}

output "rds_port" {
  description = "RDS port (empty string if RDS disabled)."
  value       = length(aws_db_instance.cns) > 0 ? tostring(aws_db_instance.cns[0].port) : ""
}

output "rds_database_name" {
  description = "RDS initial database name (matches Terraform var.rds_database_name)."
  value       = length(aws_db_instance.cns) > 0 ? aws_db_instance.cns[0].db_name : ""
}

output "rds_username" {
  description = "RDS master username (not a secret; password is never output)."
  value       = length(aws_db_instance.cns) > 0 ? aws_db_instance.cns[0].username : ""
}
