import { Link } from '../navegacao'

const CHAVE = 'sonar.consentimento'
export const VERSAO_CONSENTIMENTO = '2026-11-08'

export function consentimentoDado(): boolean {
  try {
    return localStorage.getItem(CHAVE) === VERSAO_CONSENTIMENTO
  } catch {
    return false
  }
}

export default function Consentimento({ aoAceitar }: { aoAceitar: () => void }) {
  function aceitar() {
    try {
      localStorage.setItem(CHAVE, VERSAO_CONSENTIMENTO)
    } catch {
      // sem armazenamento: o aviso volta na próxima visita
    }
    aoAceitar()
  }

  return (
    <section aria-labelledby="titulo-consentimento">
      <h1 id="titulo-consentimento" className="titulo" tabIndex={-1}>
        Antes de começar
      </h1>
      <p>
        O Sonar ajuda pessoas cegas e com baixa visão a pegar o ônibus certo. Usar o Sonar pode revelar uma deficiência
        visual, que a LGPD trata como dado sensível. Por isso:
      </p>
      <ul>
        <li>Não pedimos nome, telefone nem e-mail. Este aparelho recebe um código anônimo.</li>
        <li>A localização só serve para achar o ponto mais perto e não é gravada.</li>
        <li>As imagens da câmera do ponto nunca saem do ponto.</li>
        <li>
          O botão Falar usa o reconhecimento de voz do navegador, que pode enviar o áudio para o serviço de voz do
          fabricante (Google no Chrome, Apple no Safari). Se preferir, digite.
        </li>
        <li>A reclamação de ônibus que não parou só é enviada se você disser sim.</li>
      </ul>
      <button type="button" className="primario" onClick={aceitar}>
        Concordo e quero usar
      </button>
      <p>
        <Link para="/privacidade">Ler a política de privacidade</Link>
      </p>
    </section>
  )
}
