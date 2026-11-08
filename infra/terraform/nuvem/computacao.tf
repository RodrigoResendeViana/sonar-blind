# Amazon Linux 2023 mais recente (x86_64), lida do parâmetro público da AWS.
data "aws_ssm_parameter" "ami_al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "sonar" {
  ami                    = data.aws_ssm_parameter.ami_al2023.insecure_value
  instance_type          = var.tipo_instancia
  subnet_id              = aws_subnet.publica.id
  vpc_security_group_ids = [aws_security_group.sonar.id]
  iam_instance_profile   = aws_iam_instance_profile.sonar.name
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repositorio = var.repositorio_github
  })

  # IMDSv2 obrigatório e hop limit 1: os containers não alcançam as credenciais da EC2
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.disco_gb
    encrypted   = true
  }

  tags = {
    Name = "sonar"
  }

  # AMI nova ou mudança no user_data não recriam a máquina (o user_data só roda no 1º boot)
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# IP fixo: o registro A do domínio aponta para ele.
resource "aws_eip" "sonar" {
  domain   = "vpc"
  instance = aws_instance.sonar.id
  tags = {
    Name = "sonar"
  }
  depends_on = [aws_internet_gateway.sonar]
}
