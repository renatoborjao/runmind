export default function GoalSelection() {
  const goals = [
    "Emagrecer",
    "Correr 5 km",
    "Correr 10 km",
    "Meia Maratona",
    "Maratona",
  ];

  return (
    <section className="min-h-screen bg-black text-white flex items-center justify-center px-6">

      <div className="w-full max-w-3xl">

        <p className="text-green-500 font-semibold mb-3">
          Etapa 1 de 6
        </p>

        <h1 className="text-5xl font-bold mb-4">
          Qual é seu objetivo?
        </h1>

        <p className="text-zinc-400 mb-10 text-xl">
          Escolha o objetivo principal para que a IA monte um plano personalizado.
        </p>

        <div className="space-y-4">

          {goals.map((goal) => (
            <button
              key={goal}
              className="w-full rounded-2xl border border-zinc-700 bg-zinc-900 p-6 text-left text-xl hover:border-green-500 hover:bg-zinc-800 transition"
            >
              {goal}
            </button>
          ))}

        </div>

        <button
          className="mt-10 w-full rounded-2xl bg-green-500 py-5 text-xl font-bold hover:bg-green-400 transition"
        >
          Próximo →
        </button>

      </div>

    </section>
  );
}