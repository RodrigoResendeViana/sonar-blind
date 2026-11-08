import { useEffect, useState } from 'react'

import { useAnuncio } from '../anuncio'
import { api, mensagemDeErro, ouvirEventos } from '../api'
import { bipar, prepararSom } from '../voz'

interface Alerta {
  tipo: 'alerta' | 'ciente_registrado'
  prefixo: string
  espera_id: string
  parada_nome?: string
  paradas_ate?: number
  linha?: string
  em?: string
}

/** Gêmeo digital do Sonar Bordo: o bipper na cabine, com o botão "Ciente". */
export default function Motorista() {
  const { anunciar } = useAnuncio()
  const [alertas, setAlertas] = useState<Alerta[]>([])
  const [somAtivo, setSomAtivo] = useState(false)
  const [mensagem, setMensagem] = useState('Aguardando avisos de passageiros.')

  useEffect(
    () =>
      ouvirEventos<Alerta>('/simulador/motorista/eventos', (evento) => {
        if (evento.tipo === 'alerta') {
          setAlertas((atuais) => [...atuais.filter((a) => a.espera_id !== evento.espera_id), evento])
          bipar(3)
          const texto = `Passageiro com deficiência visual no ponto ${evento.parada_nome ?? ''}.`
          setMensagem(texto)
          anunciar(texto)
        } else if (evento.tipo === 'ciente_registrado') {
          setAlertas((atuais) => atuais.filter((a) => a.espera_id !== evento.espera_id))
        }
      }),
    [anunciar],
  )

  function ativarSom() {
    prepararSom()
    setSomAtivo(true)
    bipar(1)
  }

  async function ciente(alerta: Alerta) {
    try {
      await api.ciente(alerta.prefixo, alerta.espera_id)
      setAlertas((atuais) => atuais.filter((a) => a.espera_id !== alerta.espera_id))
      setMensagem('Ciente enviado. O passageiro foi avisado.')
      anunciar('Ciente enviado.')
    } catch (erro) {
      setMensagem(mensagemDeErro(erro))
    }
  }

  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Sonar Bordo (motorista simulado)
      </h1>
      <p>
        Esta tela faz o papel do bipper na cabine. Quando um passageiro cego espera num ponto da linha, o alerta toca
        aqui cerca de duas paradas antes.
      </p>
      {!somAtivo && (
        <button type="button" onClick={ativarSom}>
          Ativar o som do bipper
        </button>
      )}
      <p className="status">{mensagem}</p>
      {alertas.length === 0 ? (
        <p>Nenhum alerta pendente.</p>
      ) : (
        <ul className="alertas">
          {alertas.map((alerta) => (
            <li key={alerta.espera_id} className="alerta">
              <h2>Passageiro com deficiência visual</h2>
              <p>
                Ponto: <strong>{alerta.parada_nome}</strong>
                {alerta.paradas_ate ? `, a cerca de ${alerta.paradas_ate} parada(s)` : ''}
              </p>
              <p>
                Linha {alerta.linha} · ônibus {alerta.prefixo}
              </p>
              <button type="button" className="primario" onClick={() => ciente(alerta)}>
                Ciente
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
