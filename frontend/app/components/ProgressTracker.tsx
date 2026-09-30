"use client";

export type Stage = "idle" | "planning" | "researching" | "synthesizing" | "verifying" | "done" | "error";

interface ProgressTrackerProps {
  currentStage: Stage;
  detail: any;
}

const STAGES: { key: Stage; label: string; icon: string }[] = [
  { key: "planning", label: "Planner Agent", icon: "🗺" },
  { key: "researching", label: "Researcher Agents", icon: "🔍" },
  { key: "synthesizing", label: "Synthesizer Agent", icon: "✍️" },
  { key: "verifying", label: "Verifier Agent", icon: "✅" },
];

export default function ProgressTracker({ currentStage, detail }: ProgressTrackerProps) {
  if (currentStage === "idle") return null;

  const currentIdx = STAGES.findIndex((s) => s.key === currentStage);
  // When done/error, treat all stages as completed for colour purposes.
  const effectiveIdx = currentStage === "done" || currentStage === "error" ? STAGES.length : currentIdx;

  return (
    <div className="card">
      <h3 style={{ marginBottom: "1.25rem" }}>Pipeline Execution Trail</h3>

      {/* Stage row with connector lines */}
      <div style={{ position: "relative", display: "flex", alignItems: "flex-start", marginBottom: "1.5rem" }}>
        {STAGES.map((s, idx) => {
          const isActive = s.key === currentStage;
          const isDone = effectiveIdx > idx;

          let circleBg = "var(--panel-border)";
          let circleColor = "var(--text-muted)";
          let labelColor = "var(--text-muted)";

          if (isDone) {
            circleBg = "var(--success-color)";
            circleColor = "#0f172a";
            labelColor = "var(--success-color)";
          } else if (isActive) {
            circleBg = "var(--accent-primary)";
            circleColor = "#0f172a";
            labelColor = "var(--text-main)";
          }

          // Progress fraction for the connector that follows this node (0–1).
          const isLastStage = idx === STAGES.length - 1;
          // Connector is fully filled when the *next* stage is done or active.
          const connectorFill = isDone ? 1 : isActive ? 0.5 : 0;

          return (
            <div key={s.key} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>
              {/* Connector line to the right (skip for last item) */}
              {!isLastStage && (
                <div
                  style={{
                    position: "absolute",
                    top: "1rem",
                    left: "50%",
                    width: "100%",
                    height: "3px",
                    backgroundColor: "var(--panel-border)",
                    overflow: "hidden",
                    zIndex: 0,
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${connectorFill * 100}%`,
                      background: isDone
                        ? "var(--success-color)"
                        : "linear-gradient(90deg, var(--success-color), var(--accent-primary))",
                      transition: "width 0.6s ease",
                    }}
                  />
                </div>
              )}

              {/* Circle node */}
              <div
                style={{
                  position: "relative",
                  zIndex: 1,
                  width: "2rem",
                  height: "2rem",
                  borderRadius: "50%",
                  backgroundColor: circleBg,
                  color: circleColor,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: "bold",
                  fontSize: "0.875rem",
                  marginBottom: "0.5rem",
                  boxShadow: isActive ? "0 0 0 3px color-mix(in srgb, var(--accent-primary) 30%, transparent)" : "none",
                  transition: "background-color 0.3s ease, box-shadow 0.3s ease",
                }}
              >
                {isDone ? "✓" : isActive ? s.icon : idx + 1}
              </div>

              {/* Label */}
              <div
                style={{
                  fontSize: "0.8rem",
                  fontWeight: isActive ? "600" : "400",
                  color: labelColor,
                  textAlign: "center",
                  transition: "color 0.3s ease",
                }}
              >
                {s.label}
              </div>
            </div>
          );
        })}
      </div>

      {/* Status detail panel */}
      <div style={{ backgroundColor: "#0f172a", padding: "1rem", borderRadius: "0.5rem", border: "1px solid var(--panel-border)" }}>
        {currentStage === "planning" && (
          <p>Analyzing query and creating multi-angle sub-question plan…</p>
        )}
        {currentStage === "researching" && (
          <div>
            <p style={{ marginBottom: "0.5rem" }}>
              Investigating angles in parallel: <strong>{detail?.completed || 0}</strong> of{" "}
              <strong>{(detail?.completed || 0) + (detail?.remaining || 0)}</strong> completed
            </p>
            <div className="progress-bar-bg">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${
                    ((detail?.completed || 0) /
                      ((detail?.completed || 0) + (detail?.remaining || 1))) *
                    100
                  }%`,
                }}
              />
            </div>
          </div>
        )}
        {currentStage === "synthesizing" && (
          <p>Synthesizing research mini-briefs into structured draft report…</p>
        )}
        {currentStage === "verifying" && (
          <div>
            <p style={{ marginBottom: "0.5rem" }}>
              Cross-model verifier verifying claims: <strong>{detail?.completed || 0}</strong> of{" "}
              <strong>{detail?.total || detail?.claim_count || 0}</strong> claims checked
            </p>
            <div className="progress-bar-bg">
              <div
                className="progress-bar-fill"
                style={{
                  width: `${
                    ((detail?.completed || 0) /
                      (detail?.total || detail?.claim_count || 1)) *
                    100
                  }%`,
                }}
              />
            </div>
          </div>
        )}
        {currentStage === "done" && (() => {
          const report = detail?.report || detail;
          const sections = report?.sections || [];
          const survivingClaimsCount = sections.reduce(
            (acc: number, sec: any) => acc + (sec?.claims?.length || 0),
            0
          );
          const strippedCount = report?.verification_summary?.stripped || 0;

          if (survivingClaimsCount > 0) {
            return (
              <p style={{ color: "var(--success-color)", fontWeight: "500" }}>
                ✓ Research pipeline complete and fact-checked! ({survivingClaimsCount} verified claim{survivingClaimsCount === 1 ? "" : "s"} preserved)
              </p>
            );
          }

          return (
            <p style={{ color: "var(--warning-color)", fontWeight: "500" }}>
              ⚠️ Research pipeline complete, but every claim was stripped by the anti-hallucination verifier ({strippedCount} claim{strippedCount === 1 ? "" : "s"} lacked sufficient grounding in retrieved source chunks).
            </p>
          );
        })()}
      </div>
    </div>
  );
}
