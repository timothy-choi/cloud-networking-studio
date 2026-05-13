output "public_ip" {
  description = "Elastic IP attached to the Compose host."
  value       = aws_eip.cns.public_ip
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
  description = "HTTPS origin for the EC2 stack via sslip (use for smoke tests: CNS_BASE_URL + /api/health)."
  value       = "https://${aws_eip.cns.public_ip}.sslip.io"
}

output "api_base_url_sslip" {
  description = "HTTPS API base for split Vercel UI (no trailing slash path beyond /api). Caddy strips /api before proxying to FastAPI."
  value       = "https://${aws_eip.cns.public_ip}.sslip.io/api"
}

output "ssh_command" {
  description = "Example SSH command (default Ubuntu user)."
  value       = "ssh -i /path/to/${var.key_name}.pem ubuntu@${aws_eip.cns.public_ip}"
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.cns.id
}
