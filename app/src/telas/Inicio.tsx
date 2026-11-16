import { Link } from '../navegacao'

const PERFIS = [
  {
    para: '/passageiro',
    nome: 'Sou passageiro',
    descricao: 'Diga para onde quer ir: o Sonar planeja os ônibus, avisa o ponto e o motorista e diz qual ônibus chegou.',
    principal: true,
  },
  {
    para: '/motorista',
    nome: 'Sou motorista',
    descricao: 'Simula o bipper na cabine: recebe o aviso de passageiro cego no ponto e confirma com "Ciente".',
  },
  {
    para: '/ponto',
    nome: 'Ponto de ônibus',
    descricao: 'Simula o ponto: a câmera que lê o letreiro, o sensor que vê o ônibus parar e o botão do poste.',
  },
] as const

/** Porta de entrada do MVP: cada perfil leva à tela dele (sem login). */
export default function Inicio() {
  return (
    <section aria-labelledby="titulo-inicio" className="inicio">
      <h1 id="titulo-inicio" className="titulo" tabIndex={-1}>
        Bem-vindo ao Sonar
      </h1>
      <p>O copiloto de voz para pessoas cegas pegarem o ônibus certo. Como você quer entrar?</p>
      <ul className="perfis">
        {PERFIS.map((perfil) => (
          <li key={perfil.para}>
            <Link
              para={perfil.para}
              className={'principal' in perfil && perfil.principal ? 'perfil principal' : 'perfil'}
            >
              <span className="perfil-nome">{perfil.nome}</span>
              <span className="perfil-descricao">{perfil.descricao}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
