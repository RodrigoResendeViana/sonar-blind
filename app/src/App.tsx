import { useEffect, useRef, useState, type MouseEvent } from 'react'

import { ProvedorAnuncio, RegiaoAnuncio } from './anuncio'
import { Link, ROTAS, useCaminho } from './navegacao'
import Consentimento, { consentimentoDado } from './telas/Consentimento'
import Motorista from './telas/Motorista'
import Painel from './telas/Painel'
import Passageiro from './telas/Passageiro'
import Ponto from './telas/Ponto'
import Privacidade from './telas/Privacidade'

export default function App() {
  const caminho = useCaminho()
  const [consentiu, setConsentiu] = useState(consentimentoDado)
  const principal = useRef<HTMLElement>(null)
  const primeiraVez = useRef(true)

  // ao trocar de tela, o foco vai para o título: o leitor de tela anuncia onde a pessoa está
  useEffect(() => {
    if (primeiraVez.current) {
      primeiraVez.current = false
      return
    }
    principal.current?.querySelector<HTMLElement>('h1')?.focus()
  }, [caminho, consentiu])

  function pularParaConteudo(evento: MouseEvent<HTMLAnchorElement>) {
    evento.preventDefault()
    principal.current?.querySelector<HTMLElement>('h1')?.focus()
  }

  let tela
  if (caminho === '/motorista') tela = <Motorista />
  else if (caminho === '/ponto') tela = <Ponto />
  else if (caminho === '/painel') tela = <Painel />
  else if (caminho === '/privacidade') tela = <Privacidade />
  else tela = consentiu ? <Passageiro /> : <Consentimento aoAceitar={() => setConsentiu(true)} />

  return (
    <ProvedorAnuncio>
      <a className="pular" href="#conteudo" onClick={pularParaConteudo}>
        Pular para o conteúdo
      </a>
      <header>
        <nav aria-label="Telas do Sonar">
          <ul>
            {ROTAS.map((rota) => (
              <li key={rota.caminho}>
                <Link para={rota.caminho} atual={rota.caminho === caminho}>
                  {rota.nome}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="conteudo" ref={principal}>
        {tela}
        <RegiaoAnuncio />
      </main>
    </ProvedorAnuncio>
  )
}
