# Modelo de responsabilidade compartilhada

| Camada | AWS | Grupo Sonar |
|---|---|---|
| Data center, rede física, hypervisor | ✔ | |
| Serviços gerenciados (SSM, Parameter Store, S3, IAM) | ✔ disponibilidade e segurança do serviço | ✔ configuração: papéis mínimos, bucket privado e só TLS |
| Sistema operacional da EC2 (Amazon Linux 2023) | ✔ entrega a AMI atualizada | ✔ atualizar a máquina, Docker, swap, logs |
| Rede da VPC | ✔ infraestrutura | ✔ security group só com 80/443/8883, SG padrão sem regras |
| Containers e imagens | | ✔ imagens mínimas, sem root, varridas pelo Trivy a cada push |
| Aplicação e dados | | ✔ validação, limite de requisições, LGPD, backups do Postgres |
| Identidade | ✔ IAM e STS | ✔ MFA, OIDC no pipeline, nenhuma chave de longa duração |
| Segredos | ✔ cifra do Parameter Store | ✔ nada no Git (Gitleaks barra), `.env` gerado só no deploy |
| Dispositivos (ESP32) | | ✔ senha e ACL por dispositivo, TLS, firmware sem segredo no Git |
| Monitoramento | | ✔ Prometheus, alertas no Telegram |
