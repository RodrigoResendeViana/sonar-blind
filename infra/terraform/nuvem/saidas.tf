output "ip_publico" {
  description = "Elastic IP da EC2."
  value       = aws_eip.sonar.public_ip
}

output "registro_dns" {
  description = "O que criar no Registro.br."
  value       = "Registro.br > ${join(".", slice(split(".", var.dominio), 1, length(split(".", var.dominio))))} > DNS > Editar zona > Nova entrada: tipo A, nome ${split(".", var.dominio)[0]}, valor ${aws_eip.sonar.public_ip}"
}

output "id_instancia" {
  description = "Para abrir um terminal sem SSH: aws ssm start-session --target <id>."
  value       = aws_instance.sonar.id
}

output "zona" {
  value = local.zona
}

output "papel_deploy_arn" {
  description = "Vai na variável AWS_DEPLOY_ROLE_ARN do GitHub (Settings > Secrets and variables > Actions > Variables)."
  value       = aws_iam_role.deploy.arn
}

output "senha_das_metricas" {
  description = "Comando que mostra a senha do Prometheus (usuário prometheus)."
  value       = "aws ssm get-parameter --name /sonar/metricas/senha --with-decryption --query Parameter.Value --output text"
}
