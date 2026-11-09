data "aws_caller_identity" "atual" {}

# subs_github: o GitHub pode mandar o sub do OIDC no formato clássico (dono/repo) ou com os
# IDs imutáveis (dono@id/repo@id), que impedem um repositório recriado com o mesmo nome.
locals {
  conta           = data.aws_caller_identity.atual.account_id
  arn_parametros  = "arn:aws:ssm:${var.regiao}:${local.conta}:parameter/sonar"
  arn_documento   = "arn:aws:ssm:${var.regiao}::document/AWS-RunShellScript"
  subs_github     = compact([
    "repo:${var.repositorio_github}:ref:refs/heads/main",
    var.repositorio_github_ids == "" ? "" : "repo:${var.repositorio_github_ids}:ref:refs/heads/main",
  ])
}

# ---------------------------------------------------------------- papel da EC2
# SSM (deploy e sessão sem SSH) e leitura dos parâmetros /sonar/*.

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "sonar-ec2"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "ec2_parametros" {
  statement {
    sid       = "LerParametrosDoSonar"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["${local.arn_parametros}/*"]
  }
}

resource "aws_iam_role_policy" "ec2_parametros" {
  name   = "sonar-parametros"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_parametros.json
}

resource "aws_iam_instance_profile" "sonar" {
  name = "sonar-ec2"
  role = aws_iam_role.ec2.name
}

# ---------------------------------------------------------------- GitHub Actions (OIDC)
# O pipeline troca o token do GitHub por credenciais de 1 hora. Nenhuma chave fica guardada.

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.criar_provedor_oidc ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.criar_provedor_oidc ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  arn_oidc = var.criar_provedor_oidc ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.arn_oidc]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # só a branch main deste repositório pode publicar
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.subs_github
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "sonar-deploy-github"
  assume_role_policy   = data.aws_iam_policy_document.github_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "ComandoSoNaEC2DoSonar"
    actions   = ["ssm:SendCommand"]
    resources = [aws_instance.sonar.arn, local.arn_documento]
  }
  # estas duas ações não aceitam restrição por recurso
  statement {
    sid       = "AcompanharOComando"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
  statement {
    sid       = "LerDadosDoDeploy"
    actions   = ["ssm:GetParameter"]
    resources = ["${local.arn_parametros}/deploy/*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "sonar-deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
