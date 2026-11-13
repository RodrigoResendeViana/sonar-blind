/** Resumo do mapa de dados pessoais (docs/lgpd.md tem a versão completa). */
export default function Privacidade() {
  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Privacidade
      </h1>
      <p>
        Usar o Sonar pode revelar uma deficiência visual, que a LGPD trata como dado pessoal sensível (art. 5º, II). O
        Sonar foi desenhado para guardar o mínimo.
      </p>
      <h2>O que o Sonar guarda</h2>
      <ul>
        <li>Um código anônimo deste aparelho, gravado só como hash com sal.</li>
        <li>Cada espera: o ponto, as linhas, os horários do aviso ao motorista, da passagem do ônibus e do embarque.</li>
        <li>Reclamações de ônibus que não parou, com as evidências do ponto e a sua resposta (sim ou não).</li>
      </ul>
      <h2>O que o Sonar não guarda</h2>
      <ul>
        <li>Nome, telefone, e-mail ou documento.</li>
        <li>
          A sua localização: ela vai para o servidor só para planejar a viagem, avisar o ponto quando você chega e
          avisar a hora de descer. Fica na memória por algumas horas e não é gravada.
        </li>
        <li>O destino que você fala: serve só para o plano da viagem e não é gravado.</li>
        <li>Imagens: a câmera do ponto lê o letreiro ali mesmo e só manda o texto da linha.</li>
        <li>O áudio da sua voz.</li>
      </ul>
      <h2>Serviços de terceiros</h2>
      <ul>
        <li>
          Reconhecimento de voz: o botão Falar usa o recurso do navegador, que pode enviar o áudio ao serviço do
          fabricante (Google no Chrome, Apple no Safari). Digitar evita isso.
        </li>
        <li>Previsão dos ônibus: API Olho Vivo da SPTrans, consultada pelo servidor do Sonar, sem dados seus.</li>
        <li>
          Endereços: quando o destino não é um lugar conhecido, o servidor do Sonar procura o endereço no OpenStreetMap
          (Nominatim). Vai só o texto do destino, sem nada que identifique você.
        </li>
        <li>Reclamação: só vai para o SP156 se você disser sim, e não leva seu nome.</li>
      </ul>
      <p>
        Projeto acadêmico da FIAP (Global Solution 2026.2). Os dados ficam numa conta AWS do grupo e são apagados ao fim
        da avaliação.
      </p>
    </>
  )
}
