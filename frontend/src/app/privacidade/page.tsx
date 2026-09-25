import type { Metadata } from "next";

// Política de Privacidade — página PÚBLICA (sem login): exigida pelo Google pro
// "Entrar com Google" e pela LGPD (o Ritmind trata dados de saúde). Fala a
// verdade do que o app faz hoje; mudou a coleta/integração, muda aqui também.

export const metadata: Metadata = {
  title: "Privacidade · Ritmind",
  description: "Como o Ritmind coleta, usa e protege seus dados.",
};

const UPDATED = "25 de setembro de 2026";
const CONTACT = "rbfrei14@gmail.com";

export default function PrivacidadePage() {
  return (
    <main className="stage">
      <div className="phone legal" style={{ maxWidth: 680 }}>
        <header className="legal-head">
          <a href="/" className="legal-brand">Rit<b>mind</b></a>
          <h1>Política de Privacidade</h1>
          <p className="muted">Última atualização: {UPDATED}</p>
        </header>

        <section className="card">
          <p>
            O Ritmind é um treinador de corrida com inteligência artificial. Pra montar teu plano e
            acompanhar tua evolução, a gente precisa de alguns dados teus — e leva isso a sério.
            Aqui está, em linguagem simples, o que coletamos, pra que usamos e quais são os teus
            direitos, conforme a Lei Geral de Proteção de Dados (LGPD, Lei 13.709/2018).
          </p>
          <p>
            <b>Quem cuida dos teus dados (controlador):</b> Ritmind, contato{" "}
            <a className="link" href={`mailto:${CONTACT}`}>{CONTACT}</a>.
          </p>
        </section>

        <section className="card">
          <h2>1. O que coletamos</h2>
          <ul>
            <li><b>Cadastro:</b> nome, e-mail, idade, sexo, peso, altura, foto de perfil (opcional), fuso horário e, se você usa pelo Telegram/WhatsApp, o identificador da conversa.</li>
            <li><b>Objetivos e rotina:</b> meta, provas, dias disponíveis pra treinar, preferências e lesões que você nos conta.</li>
            <li><b>Treinos:</b> atividades do Strava e/ou Garmin que você conectar (distância, tempo, ritmo, frequência cardíaca, cadência, trajeto GPS), além das corridas que você grava no próprio app.</li>
            <li><b>Dados de saúde e recuperação</b> (se você conectar o Garmin): frequência cardíaca de repouso, variabilidade da FC (HRV), sono, Body Battery, estresse, VO2máx e zonas de FC. São <b>dados sensíveis</b> pela LGPD e só são tratados com o teu consentimento, dado ao conectar o relógio.</li>
            <li><b>Conversas com o coach:</b> mensagens de texto, áudios (transformados em texto) e fotos que você envia.</li>
            <li><b>Uso do app:</b> assinatura de notificações (Web Push), tênis cadastrados e, se você usar a parte social, quem você segue, curtidas e comentários.</li>
            <li><b>Acesso:</b> senha (guardada só de forma criptografada — nem nós conseguimos lê-la) e, se você entrar com Google, o identificador da tua conta Google e teu e-mail.</li>
          </ul>
        </section>

        <section className="card">
          <h2>2. Pra que usamos</h2>
          <ul>
            <li>Montar e ajustar teu plano de treino e analisar cada corrida.</li>
            <li>Avaliar tua recuperação e carga de treino, pra evitar excesso e lesão.</li>
            <li>Responder o que você pergunta ao coach e lembrar do que você já contou.</li>
            <li>Te mandar mensagens e notificações do treino (lembretes, análises, avisos).</li>
            <li>Entrar na tua conta com segurança e recuperar o acesso.</li>
          </ul>
          <p>
            Não vendemos teus dados, não usamos pra publicidade e não compartilhamos com
            ninguém além do necessário pra o app funcionar (lista abaixo).
          </p>
        </section>

        <section className="card">
          <h2>3. Com quem compartilhamos</h2>
          <p>Só com serviços que fazem o Ritmind funcionar:</p>
          <ul>
            <li><b>Google (Gemini):</b> a inteligência artificial do coach. Recebe o contexto necessário pra responder e analisar (treinos, mensagens, fotos que você manda) — nunca tua senha.</li>
            <li><b>Strava e Garmin:</b> só se você conectar. A gente lê teus treinos/saúde e, quando você pede, envia treinos pro teu relógio ou renomeia a atividade no Strava.</li>
            <li><b>Telegram e WhatsApp:</b> se você conversa com o coach por eles, as mensagens passam por esses serviços.</li>
            <li><b>Google (login):</b> se você escolher "Continuar com Google", recebemos teu nome, e-mail e identificador — nada mais.</li>
            <li><b>Oracle Cloud:</b> onde o Ritmind roda e os dados ficam guardados (servidor no Brasil).</li>
            <li><b>Microsoft OneDrive:</b> cópias de segurança (backup), pra não perder teus dados.</li>
          </ul>
          <p>
            <b>Parte social:</b> se você usar, teu nome, foto e as corridas que você deixar visíveis
            aparecem pros atletas que te seguem — de acordo com a privacidade que você escolher no Perfil
            (público ou só com solicitação). A análise do coach é sempre só tua.
          </p>
        </section>

        <section className="card">
          <h2>4. Segurança e retenção</h2>
          <p>
            Os dados trafegam criptografados (HTTPS), o acesso ao servidor é restrito e as senhas
            ficam guardadas com criptografia forte (scrypt). Guardamos teus dados enquanto tua conta
            estiver ativa. Se você pedir a exclusão, apagamos em até 30 dias — exceto o que a lei
            obrigar a manter.
          </p>
        </section>

        <section className="card">
          <h2>5. Teus direitos</h2>
          <p>Pela LGPD, você pode a qualquer momento:</p>
          <ul>
            <li>saber quais dados temos sobre você e receber uma cópia;</li>
            <li>corrigir dados errados (a maioria dá pra editar direto no Perfil);</li>
            <li>desconectar Strava ou Garmin e retirar o consentimento dos dados de saúde;</li>
            <li>pedir a exclusão da tua conta e de todos os teus dados.</li>
          </ul>
          <p>
            É só mandar um e-mail pra <a className="link" href={`mailto:${CONTACT}`}>{CONTACT}</a> ou
            pedir pro coach na conversa. Respondemos em até 15 dias.
          </p>
        </section>

        <section className="card">
          <h2>6. Menores de idade e mudanças</h2>
          <p>
            O Ritmind é pra maiores de 18 anos; menores só com autorização de um responsável. Se esta
            política mudar de forma importante, a gente te avisa pelo app ou pelo coach antes.
          </p>
        </section>

        <p className="muted center" style={{ margin: "8px 0 24px" }}>
          <a className="link" href="/">Voltar pro Ritmind</a>
        </p>
      </div>
    </main>
  );
}
