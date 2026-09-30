"use client";

import { useEffect, useState } from "react";

interface UsageData {
  server_start_time?: string;
  search?: {
    tavily?: { used: number; limit: number };
    exa?: { used: number; limit: number };
  };
  llm?: {
    groq?: { available: boolean; available_targets: string[] };
    gemini?: { available: boolean; available_targets: string[]; total_projects: number };
  };
  rate_limit?: {
    queries_today: number;
    max_queries_per_day: number;
    remaining_queries: number;
  };
}

interface UsagePanelProps {
  backendUrl: string;
  refreshTrigger?: number;
}

export default function UsagePanel({ backendUrl, refreshTrigger }: UsagePanelProps) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUsage = async () => {
    try {
      const res = await fetch(`${backendUrl}/usage`);
      if (res.ok) {
        const data = await res.json();
        setUsage(data);
      }
    } catch {
      // Keep existing usage or silent fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsage();
  }, [refreshTrigger]);

  if (loading && !usage) {
    return <div className="card"><p style={{ color: "var(--text-muted)" }}>Loading API quota & rate limit status…</p></div>;
  }

  if (!usage) return null;

  const tavily = usage.search?.tavily || { used: 0, limit: 1000 };
  const exa = usage.search?.exa || { used: 0, limit: 1400 };
  const rateLimit = usage.rate_limit || { queries_today: 0, max_queries_per_day: 30, remaining_queries: 30 };
  const startTimeFormatted = usage.server_start_time ? new Date(usage.server_start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h3>API Quotas & Usage Visibility</h3>
        {startTimeFormatted && (
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", backgroundColor: "rgba(255, 255, 255, 0.05)", padding: "0.2rem 0.5rem", borderRadius: "4px" }}>
            Tracked since restart ({startTimeFormatted})
          </span>
        )}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem", fontSize: "0.875rem" }}>
            <span>Tavily Search: {tavily.used} / {tavily.limit}</span>
            <span>{Math.round((tavily.used / tavily.limit) * 100)}%</span>
          </div>
          <div className="progress-bar-bg">
            <div className="progress-bar-fill" style={{ width: `${Math.min(100, (tavily.used / tavily.limit) * 100)}%` }} />
          </div>
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem", fontSize: "0.875rem" }}>
            <span>Exa Search (Reserve): {exa.used} / ~{exa.limit}</span>
            <span>{Math.round((exa.used / exa.limit) * 100)}%</span>
          </div>
          <div className="progress-bar-bg">
            <div className="progress-bar-fill" style={{ width: `${Math.min(100, (exa.used / exa.limit) * 100)}%`, backgroundColor: "#a855f7" }} />
          </div>
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem", fontSize: "0.875rem" }}>
            <span>Daily Queries: {rateLimit.queries_today} / {rateLimit.max_queries_per_day}</span>
            <span>{rateLimit.remaining_queries} left today</span>
          </div>
          <div className="progress-bar-bg">
            <div className="progress-bar-fill" style={{ width: `${Math.min(100, (rateLimit.queries_today / rateLimit.max_queries_per_day) * 100)}%`, backgroundColor: "#38bdf8" }} />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: "1.5rem", marginTop: "1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>
        <div>
          <strong>Gemini:</strong>{" "}
          <span style={{ color: usage.llm?.gemini?.available ? "var(--success-color)" : "var(--danger-color)" }}>
            {usage.llm?.gemini?.available ? `Active (${usage.llm.gemini.available_targets.length}/${usage.llm.gemini.total_projects} projects ready)` : "Exhausted"}
          </span>
        </div>
        <div>
          <strong>Groq:</strong>{" "}
          <span style={{ color: usage.llm?.groq?.available ? "var(--success-color)" : "var(--danger-color)" }}>
            {usage.llm?.groq?.available ? "Active" : "Exhausted"}
          </span>
        </div>
      </div>
    </div>
  );
}
