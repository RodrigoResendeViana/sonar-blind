# Segredos gerados aqui e guardados no Parameter Store (SecureString, chave aws/ssm).
# O deploy.sh lê na EC2; nada disso entra no Git ou nas imagens.
# O token do Olho Vivo NÃO passa pelo Terraform: ele é gravado à mão (docs/bootstrap.md).

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "random_password" "token_servico" {
  length  = 40
  special = false
}

resource "random_password" "sal_hash" {
  length  = 40
  special = false
}

resource "random_password" "grafana" {
  length  = 24
  special = false
}

# chave com que o n8n (RPA) cifra as credenciais que ele guarda (ex.: o bot do Telegram)
resource "random_password" "n8n" {
  length  = 40
  special = false
}

locals {
  usuarios_mqtt = toset(concat(["sonar-api"], var.usuarios_mqtt))
  segredos = {
    "/sonar/db/senha"          = random_password.db.result
    "/sonar/api/token-servico" = random_password.token_servico.result
    "/sonar/api/sal-hash"      = random_password.sal_hash.result
    "/sonar/grafana/senha"     = random_password.grafana.result
    "/sonar/n8n/chave"         = random_password.n8n.result
  }
}

resource "random_password" "mqtt" {
  for_each = local.usuarios_mqtt
  length   = 32
  special  = false
}

resource "aws_ssm_parameter" "segredo" {
  for_each = toset(keys(local.segredos))
  name     = each.key
  type     = "SecureString"
  value    = local.segredos[each.key]
}

resource "aws_ssm_parameter" "mqtt" {
  for_each = local.usuarios_mqtt
  name     = "/sonar/mqtt/usuarios/${each.key}"
  type     = "SecureString"
  value    = random_password.mqtt[each.key].result
}

resource "aws_ssm_parameter" "dominio" {
  name  = "/sonar/deploy/dominio"
  type  = "String"
  value = var.dominio
}

resource "aws_ssm_parameter" "instancia" {
  name  = "/sonar/deploy/instancia"
  type  = "String"
  value = aws_instance.sonar.id
}

resource "aws_ssm_parameter" "perfis" {
  count = var.perfis_compose == "" ? 0 : 1
  name  = "/sonar/compose/perfis"
  type  = "String"
  value = var.perfis_compose
}
