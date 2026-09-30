"use client";

import { useEffect, useRef, useState } from "react";
import QueryInput from "./components/QueryInput";
import ProgressTracker, { Stage } from "./components/ProgressTracker";
import ReportView from "./components/ReportView";
import UsagePanel from "./components/UsagePanel";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

// How long to wait for the first SSE message before showing the cold-start banner.
const COLD_START_TIMEOUT_MS = 5000;

export default function Home() {
  const [stage, setStage] = useState<Stage>("idle");
  const [detail, setDetail] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [refreshUsage, setRefreshUsage] = useState(0);
  const [isColdStarting, setIsColdStarting] = useState(false);

  const coldStartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearColdStart = () => {
    setIsColdStarting(false);
    if (coldStartTimerRef.current) {
      clearTimeout(coldStartTimerRef.current);
      coldStartTimerRef.current = null;
    }
  };

  const startResearch = (query: string) => {
    setStage("planning");
    setDetail(null);
    setReport(null);
    setErrorMsg(null);
    setIsColdStarting(false);

    // Show the cold-start banner if the backend hasn't responded within the threshold.
    coldStartTimerRef.current = setTimeout(() => {
      setIsColdStarting(true);
    }, COLD_START_TIMEOUT_MS);

    const eventSource = new EventSource(`${BACKEND_URL}/research/stream?query=${encodeURIComponent(query)}`);

    eventSource.onmessage = (event) => {
      clearColdStart(); // first message proves the backend is awake
      try {
        const data = JSON.parse(event.data);
        if (data.stage === "error") {
          setStage("error");
          setErrorMsg(data.detail?.message || "Research pipeline encountered an error.");
          eventSource.close();
          setRefreshUsage((prev) => prev + 1);
        } else if (data.stage === "done") {
          console.log("[ResearchFlow] SSE 'done' received raw payload:", data);
          const reportPayload = data.detail?.report || data.detail;
          console.log("[ResearchFlow] Extracted report payload:", reportPayload);
          setStage("done");
          setDetail(data.detail);
          setReport(reportPayload);
          eventSource.close();
          setRefreshUsage((prev) => prev + 1);
        } else {
          setStage(data.stage);
          setDetail(data.detail);
        }
      } catch (err) {
        console.error("[ResearchFlow] Failed to parse SSE event data:", err, event.data);
      }
    };

    eventSource.onerror = () => {
      clearColdStart();
      setStage("error");
      setErrorMsg("Connection to backend lost or request failed.");
      eventSource.close();
      setRefreshUsage((prev) => prev + 1);
    };
  };

  return (
    <main>
      <div style={{ textAlign: "center", marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2.5rem", marginBottom: "0.5rem", color: "var(--accent-primary)" }}>ResearchFlow</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "1.1rem" }}>
          Multi-Agent Autonomous Research Engine with Cross-Model Verification
        </p>
      </div>

      <QueryInput onSubmit={startResearch} disabled={stage !== "idle" && stage !== "done" && stage !== "error"} />

      {/* Cold-start banner — shown when the backend takes >5s to send the first SSE message */}
      {isColdStarting && (
        <div
          className="card"
          style={{
            border: "1px solid rgba(56, 189, 248, 0.3)",
            backgroundColor: "rgba(56, 189, 248, 0.07)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <span style={{ fontSize: "1.25rem", animation: "spin 1.5s linear infinite", display: "inline-block" }}>
            ⏳
          </span>
          <div>
            <strong style={{ color: "var(--accent-primary)" }}>Waking up the backend…</strong>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: "0.2rem" }}>
              The server spins down after 15 minutes of inactivity (Render free tier). Cold starts typically take
              30–60 seconds — the pipeline will begin automatically once it&apos;s ready.
            </p>
          </div>
        </div>
      )}

      {errorMsg && (
        <div className="card" style={{ border: "1px solid var(--danger-color)" }}>
          <h3 style={{ color: "var(--danger-color)", marginBottom: "0.5rem" }}>Research Request Failed</h3>
          <p>{errorMsg}</p>
        </div>
      )}

      <ProgressTracker currentStage={stage} detail={detail} />

      {report && <ReportView report={report} />}

      <UsagePanel backendUrl={BACKEND_URL} refreshTrigger={refreshUsage} />
    </main>
  );
}
