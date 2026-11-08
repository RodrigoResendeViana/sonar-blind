terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # O bucket vem do bootstrap:
  #   terraform init -backend-config="bucket=sonar-tfstate-<id-da-conta>"
  # use_lockfile: trava o state com um arquivo no próprio S3 (sem DynamoDB).
  backend "s3" {
    key          = "sonar/nuvem.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.regiao
  default_tags {
    tags = {
      Projeto       = "sonar"
      GerenciadoPor = "terraform"
      Curso         = "FIAP-GS-2026.2"
    }
  }
}
