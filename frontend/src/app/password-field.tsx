"use client";

import { useState } from "react";

// campo de senha com "mostrar"
export default function PasswordField({
  id, label, value, onChange, autoComplete, placeholder,
}: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  autoComplete: "current-password" | "new-password"; placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="pw-wrap">
        <input
          id={id}
          type={show ? "text" : "password"}
          autoComplete={autoComplete}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required
        />
        <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)}>
          {show ? "ocultar" : "mostrar"}
        </button>
      </div>
    </div>
  );
}
