import { useEffect, useState } from 'react'

import { api, mensagemDeErro, type Indicadores } from '../api'

function porcentagem(valor: number | null): string {
  return valor === null ? '—' : `${Math.round(valor * 100)}%`
}

/** Painel da cidade (gestor): só números agregados, nenhum dado pessoal. */
export default function Painel() {
  const [dados, setDados] = useState<Indicadores | null>(null)
  const [incluirDemo, setIncluirDemo] = useState(true)
  const [erro, setErro] = useState('')

  useEffect(() => {
    let ativo = true
    const carregar = () =>
      api
        .indicadores(incluirDemo)
        .then((novos) => {
          if (ativo) {
            setDados(novos)
            setErro('')
          }
        })
        .catch((falha) => ativo && setErro(mensagemDeErro(falha)))
    void carregar()
    const intervalo = setInterval(carregar, 30_000)
    return () => {
      ativo = false
      clearInterval(intervalo)
    }
  }, [incluirDemo])

  const cartoes = dados
    ? [
        { rotulo: 'Esperas', valor: String(dados.esperas) },
        { rotulo: 'Avisos ao motorista', valor: String(dados.avisos_enviados) },
        { rotulo: 'Avisos com "ciente"', valor: porcentagem(dados.taxa_ciente) },
        { rotulo: 'Embarques', valor: String(dados.embarques) },
        { rotulo: 'Embarques confirmados pela câmera', valor: String(dados.embarques_validados_camera) },
        {
          rotulo: 'Ônibus que não pararam a cada 100 esperas',
          valor: dados.nao_parou_por_100_esperas === null ? '—' : String(dados.nao_parou_por_100_esperas),
        },
        {
          rotulo: 'Tempo médio de espera',
          valor: dados.tempo_medio_espera_min === null ? '—' : `${dados.tempo_medio_espera_min} min`,
        },
      ]
    : []

  return (
    <>
      <h1 className="titulo" tabIndex={-1}>
        Painel da cidade
      </h1>
      <p>Indicadores dos últimos 30 dias. Atualiza a cada 30 segundos.</p>
      <label className="opcao">
        <input type="checkbox" checked={incluirDemo} onChange={(evento) => setIncluirDemo(evento.target.checked)} />
        Incluir as demonstrações
      </label>
      {erro && <p className="status">{erro}</p>}
      {dados && (
        <>
          <dl className="cartoes">
            {cartoes.map((cartao) => (
              <div key={cartao.rotulo} className="cartao">
                <dt>{cartao.rotulo}</dt>
                <dd>{cartao.valor}</dd>
              </div>
            ))}
          </dl>

          <h2>Por linha</h2>
          {dados.por_linha.length === 0 ? (
            <p>Ainda sem esperas no período.</p>
          ) : (
            <div className="rolagem">
              <table>
                <caption className="so-leitor">Esperas, avisos e paradas perdidas por linha</caption>
                <thead>
                  <tr>
                    <th scope="col">Linha</th>
                    <th scope="col">Esperas</th>
                    <th scope="col">Avisos</th>
                    <th scope="col">Ciente</th>
                    <th scope="col">Embarques</th>
                    <th scope="col">Não parou</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.por_linha.map((linha) => (
                    <tr key={linha.linha}>
                      <th scope="row">{linha.linha}</th>
                      <td>{linha.esperas ?? 0}</td>
                      <td>{linha.avisos ?? 0}</td>
                      <td>{linha.cientes ?? 0}</td>
                      <td>{linha.embarques ?? 0}</td>
                      <td>{linha.nao_parou ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h2>Dispositivos</h2>
          {dados.dispositivos.length === 0 ? (
            <p>Nenhum Sonar Ponto ou Sonar Bordo conectado ainda.</p>
          ) : (
            <ul>
              {dados.dispositivos.map((d) => (
                <li key={`${d.tipo}-${d.id}`}>
                  {d.tipo} {d.id}: {d.online ? 'online' : 'offline'}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}
