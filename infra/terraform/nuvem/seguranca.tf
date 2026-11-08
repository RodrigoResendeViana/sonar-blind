# Entrada só por 80, 443 e 8883. Não há porta 22: a administração é pelo SSM.
resource "aws_security_group" "sonar" {
  name        = "sonar"
  description = "Sonar: HTTP, HTTPS e MQTT com TLS. Sem porta de administracao."
  vpc_id      = aws_vpc.sonar.id
  tags = {
    Name = "sonar"
  }
}

locals {
  entradas = {
    http = {
      porta     = 80
      protocolo = "tcp"
      descricao = "HTTP: redireciona para HTTPS e valida o Lets Encrypt"
    }
    https = {
      porta     = 443
      protocolo = "tcp"
      descricao = "HTTPS do app e da API"
    }
    http3 = {
      porta     = 443
      protocolo = "udp"
      descricao = "HTTP/3 (QUIC)"
    }
    mqtt_tls = {
      porta     = 8883
      protocolo = "tcp"
      descricao = "MQTT com TLS: Sonar Ponto, camera e Sonar Bordo"
    }
  }
}

resource "aws_vpc_security_group_ingress_rule" "entrada" {
  for_each          = local.entradas
  security_group_id = aws_security_group.sonar.id
  description       = each.value.descricao
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = each.value.protocolo
  from_port         = each.value.porta
  to_port           = each.value.porta
}

resource "aws_vpc_security_group_egress_rule" "saida" {
  security_group_id = aws_security_group.sonar.id
  description       = "Saida: imagens do GHCR, SSM, Olho Vivo e Lets Encrypt"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# O security group padrão da VPC fica sem nenhuma regra.
resource "aws_default_security_group" "padrao" {
  vpc_id = aws_vpc.sonar.id
}
