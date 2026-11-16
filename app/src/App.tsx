import { useEffect, useRef, useState, type MouseEvent } from 'react'

import { ProvedorAnuncio, RegiaoAnuncio } from './anuncio'
import { Link, useCaminho } from './navegacao'
import Consentimento, { consentimentoDado } from './telas/Consentimento'
import Inicio from './telas/Inicio'
import Motorista from './telas/Motorista'
import Passageiro from './telas/Passageiro'
import Ponto from './telas/Ponto'

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
  if (caminho === '/passageiro') {
    tela = consentiu ? <Passageiro /> : <Consentimento aoAceitar={() => setConsentiu(true)} />
  } else if (caminho === '/motorista') tela = <Motorista />
  else if (caminho === '/ponto') tela = <Ponto />
  else tela = <Inicio />

  return (
    <ProvedorAnuncio>
      {caminho !== '/' && (
        <>
          <a className="pular" href="#conteudo" onClick={pularParaConteudo}>
            Pular para o conteúdo
          </a>
          {/* sem menu: a pessoa escolhe o perfil no início; daqui só se volta para lá */}
          <header>
            <Link para="/" className="voltar">
              <span aria-hidden="true">←</span> Início
            </Link>
          </header>
        </>
      )}
      <main id="conteudo" ref={principal}>
        {tela}
        <RegiaoAnuncio />
      </main>
    </ProvedorAnuncio>
  )
}
