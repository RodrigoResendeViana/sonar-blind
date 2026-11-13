# Mapa de dados pessoais (LGPD)

Usar o Sonar revela deficiência visual, que é dado pessoal sensível (LGPD, art. 5º, II). A base
legal é o consentimento específico e destacado (art. 11, I), pedido na primeira tela do app. O
desenho segue a minimização (art. 6º, III): o Sonar não sabe quem é o usuário.

| Dado | Onde fica | Para quê | Quanto tempo | Quem acessa |
|---|---|---|---|---|
| Id anônimo do aparelho | celular (localStorage); na API, só o SHA-256 com sal | agrupar as esperas do mesmo aparelho | até o fim do projeto | ninguém consegue voltar ao id |
| Localização | memória do app e da API (sessão da conversa) | planejar a viagem, avisar o ponto ao chegar, avisar a hora de descer | some com a sessão (até 6 h); não vai para o banco | — |
| Destino falado | memória da API (sessão da conversa) | planejar a viagem; endereço desconhecido é procurado no OpenStreetMap (Nominatim) pelo servidor, sem dado do usuário | some com a sessão; não vai para o banco | OpenStreetMap (só o texto do destino) |
| Espera (ponto, linhas, horários) | Postgres na EC2 | avisar o motorista, validar o embarque, indicadores | até o fim do projeto | API; painel vê só agregados |
| Ocorrência com evidências | Postgres na EC2 | reclamação no SP156, só com "sim" do usuário | até o fim do projeto | robô de RPA (com token) |
| Imagem da câmera | memória do notebook do ponto | ler o letreiro | descartada na hora; nunca sai do ponto | — |
| Texto da linha lida | MQTT e Postgres | dizer "é o seu" | até o fim do projeto | API |
| Áudio da voz | serviço de voz do navegador (Google no Chrome, Apple no Safari) | transcrever a pergunta | regra do fabricante | fabricante do navegador |
| Logs | Docker na EC2 (10 MB × 3 por serviço) | operação | rotação automática | grupo |

**Operador de terceiros.** O reconhecimento de voz do navegador é o único ponto em que um dado
do usuário sai do Sonar. A tela de consentimento avisa isso e oferece o campo de texto como
alternativa.

**Direitos do titular.** Como não há identificação, o pedido de exclusão é atendido apagando o
id anônimo no próprio celular (limpar os dados do site); as esperas ficam sem vínculo.

**Fim do projeto.** Depois da correção, `terraform destroy` apaga a EC2, o disco e os parâmetros
(docs/bootstrap.md, passo 10).
