# Nem toda zona de disponibilidade tem todo tipo de instância: escolhe uma que tenha.
data "aws_ec2_instance_type_offerings" "disponivel" {
  location_type = "availability-zone"
  filter {
    name   = "instance-type"
    values = [var.tipo_instancia]
  }
}

locals {
  zona = sort(data.aws_ec2_instance_type_offerings.disponivel.locations)[0]
}

resource "aws_vpc" "sonar" {
  cidr_block           = var.cidr_vpc
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "sonar"
  }
}

resource "aws_internet_gateway" "sonar" {
  vpc_id = aws_vpc.sonar.id
  tags = {
    Name = "sonar"
  }
}

# A sub-rede não dá IP público automático: a EC2 usa só o Elastic IP.
resource "aws_subnet" "publica" {
  vpc_id            = aws_vpc.sonar.id
  cidr_block        = cidrsubnet(var.cidr_vpc, 8, 1)
  availability_zone = local.zona
  tags = {
    Name = "sonar-publica"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.sonar.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sonar.id
  }
  tags = {
    Name = "sonar-publica"
  }
}

resource "aws_route_table_association" "publica" {
  subnet_id      = aws_subnet.publica.id
  route_table_id = aws_route_table.publica.id
}
