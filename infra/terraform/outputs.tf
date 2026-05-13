output "public_ip" {
  description = "Elastic IP attached to the Compose host."
  value       = aws_eip.cns.public_ip
}

output "public_url" {
  description = "HTTP URL for the stack (same host as Caddy on port 80 after you deploy Compose)."
  value       = "http://${aws_eip.cns.public_ip}"
}

output "ssh_command" {
  description = "Example SSH command (default Ubuntu user)."
  value       = "ssh -i /path/to/${var.key_name}.pem ubuntu@${aws_eip.cns.public_ip}"
}

output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.cns.id
}
