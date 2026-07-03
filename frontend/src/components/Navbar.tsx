export default function Navbar() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-black/80 backdrop-blur border-b border-neutral-800">

      <div className="max-w-7xl mx-auto flex items-center justify-between px-8 py-5">

        <h1 className="text-2xl font-extrabold text-white">
          Run<span className="text-green-500">Mind</span>
        </h1>

        <nav className="hidden md:flex gap-10 text-gray-300">

          <a href="#">Recursos</a>

          <a href="#">Preços</a>

          <a href="#">Sobre</a>

        </nav>

        <div className="flex gap-3">

          <button className="text-white px-5">
            Entrar
          </button>

          <button className="bg-green-500 hover:bg-green-400 transition rounded-xl px-5 py-2 font-bold">
            Começar
          </button>

        </div>

      </div>

    </header>
  );
}