interface Props {
  sender: "ai" | "user";
  text: string;
}

export default function Message({ sender, text }: Props) {
  const isAI = sender === "ai";

  return (
    <div
      className={`flex mb-6 ${
        isAI ? "justify-start" : "justify-end"
      }`}
    >
      <div
        className={`max-w-xl rounded-3xl px-6 py-5 ${
          isAI
            ? "bg-zinc-800 text-white"
            : "bg-green-600 text-white"
        }`}
      >
        <p className="text-xs opacity-60 mb-2">
          {isAI ? "🤖 Coach IA" : "Você"}
        </p>

        <p className="leading-8 text-lg">
          {text}
        </p>
      </div>
    </div>
  );
}