variable "regiao" {
  description = "Região da AWS."
  type        = string
  default     = "us-east-1"
}

variable "dominio" {
  description = "Nome público do Sonar. O registro A é criado à mão no Registro.br."
  type        = string
  default     = "sonar.rodrigoviana.app.br"
}

variable "repositorio_github" {
  description = "dono/repositório que pode publicar na EC2 pelo OIDC (só a branch main)."
  type        = string
  default     = "RodrigoResendeViana/sonar-blind"
}

variable "repositorio_github_ids" {
  description = "O mesmo repositório no formato com IDs do sub do OIDC (dono@id/repo@id). Vazio desliga."
  type        = string
  default     = "RodrigoResendeViana@127115158/sonar-blind@1450728497"
}

variable "tipo_instancia" {
  description = "8 GiB por causa do LLM local. Contas no plano gratuito só aceitam alguns tipos; m7i-flex.large é um deles."
  type        = string
  default     = "m7i-flex.large"
}

variable "disco_gb" {
  description = "Tamanho do disco gp3 da EC2."
  type        = number
  default     = 30
}

variable "email_alertas" {
  description = "E-mail que recebe os alertas do AWS Budgets."
  type        = string
}

variable "limite_orcamento_usd" {
  description = "Teto mensal do AWS Budgets, em dólares (os créditos de conta nova cobrem o gasto)."
  type        = number
  default     = 40
}

variable "usuarios_mqtt" {
  description = "Dispositivos com senha própria no Mosquitto: ponto-<parada>, camera-<parada>, bordo-<prefixo>."
  type        = list(string)
  default     = ["ponto-demo", "camera-demo", "bordo-90001"]

  validation {
    condition     = alltrue([for usuario in var.usuarios_mqtt : can(regex("^(ponto|camera|bordo)-[A-Za-z0-9-]{1,40}$", usuario))])
    error_message = "Cada usuário deve ser ponto-<parada>, camera-<parada> ou bordo-<prefixo>."
  }
}

variable "perfis_compose" {
  description = "Perfis extras do docker compose. Use \"ia\" para subir o Ollama."
  type        = string
  default     = ""
}

variable "criar_provedor_oidc" {
  description = "false se a conta já tiver o provedor OIDC do GitHub."
  type        = bool
  default     = true
}

variable "cidr_vpc" {
  description = "Faixa de IPs da VPC do Sonar."
  type        = string
  default     = "10.42.0.0/16"
}
