import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'

import { falarEmVozAlta } from './voz'

interface Anunciador {
  mensagem: string
  anunciar: (texto: string) => void
  vozAlta: boolean
  setVozAlta: (valor: boolean) => void
}

const Contexto = createContext<Anunciador>({ mensagem: '', anunciar: () => {}, vozAlta: false, setVozAlta: () => {} })

const CHAVE_VOZ = 'sonar.voz-alta'

function lerPreferencia(): boolean {
  try {
    return localStorage.getItem(CHAVE_VOZ) === 'sim'
  } catch {
    return false
  }
}

/**
 * Uma região aria-live só: o TalkBack ou o VoiceOver lê as respostas com a voz e a
 * velocidade que a pessoa escolheu, sem duas vozes falando juntas. "Ler em voz alta"
 * (síntese do navegador) é opcional, para quem não usa leitor de tela.
 */
export function ProvedorAnuncio({ children }: { children: ReactNode }) {
  const [mensagem, setMensagem] = useState('')
  const [vozAlta, setVozAltaEstado] = useState(lerPreferencia)
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)

  const anunciar = useCallback(
    (texto: string) => {
      // limpa e escreve de novo, para o leitor de tela repetir mesmo um texto igual
      setMensagem('')
      if (temporizador.current) clearTimeout(temporizador.current)
      temporizador.current = setTimeout(() => setMensagem(texto), 60)
      if (vozAlta) falarEmVozAlta(texto)
    },
    [vozAlta],
  )

  const setVozAlta = useCallback((valor: boolean) => {
    setVozAltaEstado(valor)
    try {
      localStorage.setItem(CHAVE_VOZ, valor ? 'sim' : 'nao')
    } catch {
      // sem armazenamento: vale só nesta sessão
    }
  }, [])

  return <Contexto.Provider value={{ mensagem, anunciar, vozAlta, setVozAlta }}>{children}</Contexto.Provider>
}

/** Fica dentro do <main>, invisível na tela; quem enxerga lê o cartão de status de cada tela. */
export function RegiaoAnuncio() {
  const { mensagem } = useContext(Contexto)
  return (
    <div className="so-leitor" aria-live="assertive" aria-atomic="true" data-testid="anuncio">
      {mensagem}
    </div>
  )
}

export const useAnuncio = () => useContext(Contexto)
