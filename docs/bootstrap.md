# Primeira subida: o passo a passo do Rodrigo

O que só você pode fazer, porque exige as suas contas. Leva cerca de 1 hora; os passos 5 e 6
dependem da propagação do DNS (minutos a algumas horas).

## 1. GitHub

1. Deixe o repositório **público** (Settings > General > Danger Zone > Change visibility). A FIAP
   pede links públicos, e a EC2 baixa o código por `git clone` sem senha.
2. Se o código veio num zip: clone o repositório, copie o conteúdo do zip para dentro dele,
   `git checkout -b fundacao`, `git add -A`, `git commit -m "Fundação do Sonar"`,
   `git push -u origin fundacao` e abra um pull request para a `main`. O pipeline roda no PR.

## 2. Conta AWS

1. Ative o MFA do usuário raiz (menu da conta > Credenciais de segurança).
2. Para o dia a dia, crie um usuário IAM `rodrigo-admin` com a política `AdministratorAccess` e
   MFA, e entre com ele. Use sempre a região **us-east-1 (Norte da Virgínia)**.
3. Abra o **CloudShell** (ícone `>_` no topo do console). Tudo abaixo roda lá.

## 3. Terraform no CloudShell

O CloudShell guarda só a pasta pessoal entre sessões, então o Terraform vai para `~/bin`:

```bash
TF=1.17.1
mkdir -p ~/bin && cd /tmp
curl -fsSLO https://releases.hashicorp.com/terraform/$TF/terraform_${TF}_linux_amd64.zip
curl -fsSLO https://releases.hashicorp.com/terraform/$TF/terraform_${TF}_SHA256SUMS
grep linux_amd64.zip terraform_${TF}_SHA256SUMS | sha256sum -c -
unzip -o terraform_${TF}_linux_amd64.zip -d ~/bin
grep -q 'HOME/bin' ~/.bashrc || echo 'export PATH=$HOME/bin:$PATH' >> ~/.bashrc
export PATH=$HOME/bin:$PATH && terraform version

cd ~ && git clone https://github.com/RodrigoResendeViana/sonar-blind.git sonar && cd sonar
```

### 3.1 Bucket do state (uma vez só)

```bash
cd ~/sonar/infra/terraform/bootstrap
terraform init && terraform apply
```

Guarde o `terraform.tfstate` desta pasta: ele só existe no CloudShell (é pequeno e não tem segredo).

### 3.2 A infraestrutura

```bash
cd ~/sonar/infra/terraform/nuvem
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars          # coloque o seu e-mail em email_alertas
terraform init -backend-config="bucket=sonar-tfstate-$(aws sts get-caller-identity --query Account --output text)"
terraform plan
terraform apply
```

A saída mostra o `ip_publico`, o `registro_dns` e o `papel_deploy_arn`. Para ver de novo:
`terraform output`.

Se o `apply` reclamar do tipo de instância, a conta pode ter outra lista de tipos liberados no
plano gratuito: veja em EC2 > Tipos de instância (filtro "Free tier eligible") e mude
`tipo_instancia` no `terraform.tfvars` para um de 8 GiB, ou de 4 GiB sem o LLM local.

## 4. Token do Olho Vivo

Crie o token em sptrans.com.br/desenvolvedores (Meus aplicativos) e grave no Parameter Store,
sem deixar no histórico do terminal:

```bash
read -rsp "Token do Olho Vivo: " TOKEN && echo
aws ssm put-parameter --name /sonar/olhovivo/token --type SecureString --value "$TOKEN" --overwrite
unset TOKEN
```

Sem o token, o Sonar sobe só com o modo demonstração.

## 5. Domínio no Registro.br

registro.br > entrar > `rodrigoviana.app.br` > **DNS** > **Editar zona** > **Nova entrada**:

| Tipo | Nome | Dados |
|---|---|---|
| A | `sonar` | o `ip_publico` do Terraform |

Salve e confira (pode levar de minutos a algumas horas): `nslookup sonar.rodrigoviana.app.br`.
O seu servidor local não entra aqui: ele não precisa de IP público.

## 6. Pipeline

1. No GitHub: Settings > Secrets and variables > Actions > aba **Variables** > New repository
   variable: `AWS_DEPLOY_ROLE_ARN` = o `papel_deploy_arn` do Terraform. É só isso: o pipeline usa
   OIDC, então **não existe chave da AWS** para cadastrar.
2. Faça o merge do pull request (ou um push na `main`). O pipeline testa, publica as imagens no
   GHCR e faz o deploy pelo SSM.
3. Na primeira vez, as imagens podem nascer privadas. Se o deploy falhar no `docker compose pull`:
   github.com/RodrigoResendeViana?tab=packages > `sonar-api` > Package settings > Change
   visibility > Public; o mesmo para `sonar-web`; depois, Re-run failed jobs.
4. Se o DNS ainda não tinha propagado no primeiro deploy, o MQTT sobe sem a porta 8883. Quando
   `https://sonar.rodrigoviana.app.br` abrir com cadeado, rode o deploy de novo (Actions >
   ci-cd > Run workflow, na `main`).

Teste: `https://sonar.rodrigoviana.app.br` (o app), `/api/docs` (a API) e o botão "Ver a
jornada completa".

**Terminal na EC2, sem SSH:** `aws ssm start-session --target <id_instancia>` no CloudShell.
**Voltar uma versão:** em Actions, abra a execução de um commit antigo da `main` e clique em
Re-run all jobs.

## 7. Firmware e câmera

As senhas MQTT de cada dispositivo:

```bash
for u in ponto-demo camera-demo bordo-90001; do
  echo "$u: $(aws ssm get-parameter --name /sonar/mqtt/usuarios/$u --with-decryption --query Parameter.Value --output text)"
done
```

Elas vão no `firmware/include/secrets.h` (veja `firmware/README.md`) e nas variáveis do
serviço da câmera (`edge/README.md`). Para mais dispositivos, acrescente em `usuarios_mqtt` no
`terraform.tfvars`, rode `terraform apply` e o deploy de novo.

## 8. Monitoramento no servidor local

Siga `infra/monitoramento/README.md`: bot do Telegram, três arquivos de senha e
`docker compose up -d`.

## 9. Prints para o PDF de DevOps

- Actions: uma execução verde completa e a execução barrada pelo Trivy (`docs/execucao-barrada.md`).
- Terraform: `terraform apply` com os recursos criados e o `terraform output`.
- AWS: EC2 com o papel do SSM, security group só com 80/443/8883, Parameter Store com os
  parâmetros `/sonar/*` (sem mostrar valores), AWS Budgets.
- GHCR com as duas imagens; o app aberto no domínio com cadeado.
- Grafana com o painel "Sonar — sinais de ouro" e um alerta chegando no Telegram.

## 10. Depois da correção

Para não gastar créditos à toa: `terraform destroy` em `nuvem` e depois em `bootstrap` (antes,
esvazie o bucket: `aws s3 rm s3://sonar-tfstate-<conta> --recursive` e apague as versões no
console), apague o registro A e, se quiser, os pacotes do GHCR.
