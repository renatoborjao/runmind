export default function HowItWorks() {
  const steps = [
    {
      number: "01",
      title: "Defina seu objetivo",
      text: "Informe sua meta, distância, ritmo e disponibilidade."
    },
    {
      number: "02",
      title: "A IA cria o plano",
      text: "Receba treinos inteligentes adaptados ao seu perfil."
    },
    {
      number: "03",
      title: "Evolua diariamente",
      text: "O RunMind ajusta automaticamente seu plano conforme sua evolução."
    }
  ];

  return (
    <section className="py-28 px-6 bg-[#050505]">
      <div className="max-w-6xl mx-auto">

        <h2 className="text-5xl font-bold text-center mb-16">
          Como funciona
        </h2>

        <div className="grid md:grid-cols-3 gap-8">

          {steps.map((step)=>(
            <div
              key={step.number}
              className="rounded-3xl border border-zinc-800 bg-zinc-900 p-8 hover:border-green-500 transition"
            >
              <p className="text-green-500 text-4xl font-bold mb-6">
                {step.number}
              </p>

              <h3 className="text-2xl font-bold mb-4">
                {step.title}
              </h3>

              <p className="text-zinc-400 leading-8">
                {step.text}
              </p>

            </div>
          ))}

        </div>

      </div>
    </section>
  );
}