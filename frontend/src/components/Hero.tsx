export default function Hero() {
  return (
    <section className="min-h-screen bg-black text-white flex items-center justify-center px-6">
      <div className="max-w-5xl w-full text-center">

        <div className="inline-flex items-center rounded-full border border-green-500/30 bg-green-500/10 px-4 py-2 mb-8">
          <span className="text-green-400 text-sm font-semibold">
            🚀 Powered by Artificial Intelligence
          </span>
        </div>

        <h1 className="text-7xl font-extrabold tracking-tight">
          RunMind
        </h1>

        <p className="mt-8 text-2xl text-gray-400 max-w-3xl mx-auto leading-relaxed">
          Seu treinador inteligente para corrida.
          <br />
          Planos personalizados, evolução automática e análise completa dos seus treinos.
        </p>

        <div className="mt-12 flex justify-center gap-5">
          <button className="rounded-xl bg-green-500 hover:bg-green-400 transition px-8 py-4 text-lg font-bold">
            Criar meu Plano
          </button>

          <button className="rounded-xl border border-white hover:bg-white hover:text-black transition px-8 py-4 text-lg font-bold">
            Fazer Login
          </button>
        </div>

        <div className="grid grid-cols-3 gap-8 mt-24">

          <div className="rounded-2xl border border-neutral-800 p-8 bg-neutral-900/50">
            <div className="text-5xl mb-4">🏃</div>

            <h3 className="text-xl font-bold mb-2">
              Treinos Inteligentes
            </h3>

            <p className="text-gray-400">
              IA cria treinos personalizados para o seu objetivo.
            </p>
          </div>

          <div className="rounded-2xl border border-neutral-800 p-8 bg-neutral-900/50">
            <div className="text-5xl mb-4">📈</div>

            <h3 className="text-xl font-bold mb-2">
              Evolução
            </h3>

            <p className="text-gray-400">
              Acompanhe ritmo, pace, frequência cardíaca e desempenho.
            </p>
          </div>

          <div className="rounded-2xl border border-neutral-800 p-8 bg-neutral-900/50">
            <div className="text-5xl mb-4">🤖</div>

            <h3 className="text-xl font-bold mb-2">
              Coach IA
            </h3>

            <p className="text-gray-400">
              Receba recomendações automáticas todos os dias.
            </p>
          </div>

        </div>

      </div>
    </section>
  );
}