"use client";

import { useState } from "react";

interface QueryInputProps {
  onSubmit: (query: string) => void;
  disabled: boolean;
}

export default function QueryInput({ onSubmit, disabled }: QueryInputProps) {
  const [query, setQuery] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !disabled) {
      onSubmit(query.trim());
    }
  };

  return (
    <div className="card">
      <h2 style={{ marginBottom: "0.5rem" }}>Deep Research Query</h2>
      <p style={{ color: "var(--text-muted)", marginBottom: "1rem", fontSize: "0.95rem" }}>
        Enter an open-ended topic. The multi-agent workflow will plan, research, synthesize, and verify claims.
      </p>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: "0.75rem" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. Compare solid state vs lithium ion battery commercialization by 2030"
          disabled={disabled}
          style={{
            flex: 1,
            padding: "0.75rem 1rem",
            borderRadius: "0.5rem",
            border: "1px solid var(--panel-border)",
            backgroundColor: "#0f172a",
            color: "var(--text-main)",
            fontSize: "1rem",
          }}
        />
        <button type="submit" className="btn-primary" disabled={disabled || !query.trim()}>
          {disabled ? "Searching…" : "Search"}
        </button>
      </form>
    </div>
  );
}
