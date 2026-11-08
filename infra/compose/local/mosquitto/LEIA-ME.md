Pasta vazia de propósito. Em produção, o `deploy.sh` grava aqui o arquivo de senhas,
a ACL e o certificado TLS do Mosquitto (em `/opt/sonar/segredos/mosquitto`, fora do Git).
Na sua máquina, o broker roda sem senha e só aceita conexões de `127.0.0.1`.
