# Custo na AWS

Conta nova no plano gratuito: US$ 100 em créditos, válidos até 08/05/2027. Período de uso: de
10/11 a 26/11/2026 (fim da janela de correção), 16 dias ou 384 horas.

| Item | Conta | Custo estimado |
|---|---|---|
| EC2 m7i-flex.large (2 vCPU, 8 GiB), us-east-1, sob demanda | 384 h × US$ 0,0958 | US$ 36,79 |
| EBS gp3 30 GB | 30 GB × US$ 0,08/GB-mês × 16/30 | US$ 1,28 |
| IPv4 público (Elastic IP) | 384 h × US$ 0,005 | US$ 1,92 |
| S3 do state, Parameter Store (padrão), SSM, AWS Budgets (2 primeiros) | uso mínimo | ~US$ 0 |
| Transferência de saída | abaixo de 100 GB/mês | US$ 0 |
| **Total** | | **~US$ 40 dos US$ 100** |

O AWS Budgets do Terraform avisa por e-mail em 50%, 80% e 100% de US$ 40/mês, contando o uso
antes dos créditos. Para economizar: pare a EC2 quando ninguém estiver avaliando
(`aws ec2 stop-instances --instance-ids <id>`; o Elastic IP e o disco continuam cobrando pouco).

Sem o LLM local (perfil `ia` desligado), uma t3.small de 2 GiB bastaria, por cerca de US$ 8 no
mesmo período. Confira os preços na calculadora da AWS antes de fechar o PDF.

Fora da AWS: o domínio, que o grupo já tinha (e o Airflow do Big Data, que roda onde a equipe escolher).
