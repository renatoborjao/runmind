import { initialMessages } from "@/services/chat";
import Message from "@/components/chat/Message";

export default function CoachChat() {
  return (
    <section>

      {initialMessages.map((msg) => (
        <Message
          key={msg.id}
          sender={msg.sender}
          text={msg.text}
        />
      ))}

    </section>
  );
}