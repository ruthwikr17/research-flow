"use client";

import { useState } from "react";

interface Claim {
  id: string;
  text: string;
  supporting_source_urls?: string[];
  verdict?: {
    verdict: string;
    confidence: number;
    audit_source_url?: string;
    audit_chunk_text?: string;
    reasoning: string;
    error?: string;
  };
}

interface Section {
  title: string;
  claims: Claim[];
  narrative?: string;
}

interface VerifiedReport {
  original_query: string;
  title?: string;
  intro: string;
  sections: Section[];
  conclusion: string;
  all_sources: { url: string; title: string; snippet: string; search_provider: string }[];
  verification_summary?: {
    total_claims: number;
    supported: number;
    partially_supported: number;
    unverified?: number;
    stripped: number;
    stripped_claims?: string[];
  };
}

interface ReportViewProps {
  report: VerifiedReport;
}

function formatVerdict(verdict: string): string {
  switch (verdict?.toLowerCase()) {
    case "supported":
      return "Supported";
    case "partially_supported":
      return "Partially Supported";
    case "unsupported":
      return "Unsupported";
    case "unverified":
      return "Unverified";
    default:
      return verdict ? verdict.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "Unverified";
  }
}

function getConfidenceDescription(verdict: string, confidence: number): string {
  const pct = Math.round(confidence * 100);
  switch (verdict?.toLowerCase()) {
    case "supported":
      return `Verifier is ${pct}% confident this claim is fully supported`;
    case "partially_supported":
      return `Verifier is ${pct}% confident this is a partial match`;
    case "unsupported":
      return `Verifier is ${pct}% confident this claim is unsupported`;
    case "unverified":
      return `Verifier was unable to confirm claim (${pct}% confidence)`;
    default:
      return `Verifier is ${pct}% confident in this verdict`;
  }
}

function isUnverified(claim: Claim): boolean {
  const v = claim.verdict?.verdict?.toLowerCase();
  return !v || v === "unverified";
}

/** A single claim card — used for both verified and unverified groups. */
function ClaimCard({
  claim,
  expandedClaim,
  onToggle,
  dimmed = false,
}: {
  claim: Claim;
  expandedClaim: string | null;
  onToggle: (id: string) => void;
  dimmed?: boolean;
}) {
  const isExpanded = expandedClaim === claim.id;
  const verdict = claim.verdict;
  const verdictType = verdict?.verdict?.toLowerCase() || "unverified";

  const badgeClass =
    verdictType === "supported"
      ? "badge-supported"
      : verdictType === "partially_supported"
      ? "badge-partially"
      : verdictType === "unverified"
      ? "badge-unverified"
      : "badge-unsupported";

  return (
    <div
      style={{
        backgroundColor: dimmed ? "rgba(15,23,42,0.5)" : "#0f172a",
        border: dimmed
          ? "1.5px dashed rgba(148,163,184,0.35)"
          : "1px solid var(--panel-border)",
        borderRadius: "0.5rem",
        padding: "1rem",
        opacity: dimmed ? 0.75 : 1,
        transition: "opacity 0.2s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
        <p style={{ flex: 1, fontSize: "0.95rem", color: dimmed ? "var(--text-muted)" : "var(--text-main)" }}>
          {claim.text}
        </p>
        {verdict && (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", flexShrink: 0 }}>
            <span className={`badge ${badgeClass}`}>
              {formatVerdict(verdict.verdict)}
            </span>
            {verdict.confidence > 0 && (
              <span
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  marginTop: "0.25rem",
                  textAlign: "right",
                }}
              >
                {getConfidenceDescription(verdict.verdict, verdict.confidence)}
              </span>
            )}
          </div>
        )}
      </div>

      {claim.supporting_source_urls && claim.supporting_source_urls.length > 0 && (
        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Sources:{" "}
          {claim.supporting_source_urls.map((url, uidx) => (
            <a key={uidx} href={url} target="_blank" rel="noreferrer" style={{ marginRight: "0.5rem" }}>
              [{uidx + 1}]
            </a>
          ))}
        </div>
      )}

      {verdict && (
        <button
          onClick={() => onToggle(claim.id)}
          style={{
            background: "none",
            border: "none",
            color: dimmed ? "var(--text-muted)" : "var(--accent-primary)",
            fontSize: "0.8rem",
            cursor: "pointer",
            marginTop: "0.5rem",
            padding: 0,
          }}
        >
          {isExpanded ? "▲ Hide verifier audit trail" : "▼ View verifier audit trail"}
        </button>
      )}

      {isExpanded && verdict && (
        <div
          style={{
            marginTop: "0.75rem",
            padding: "0.75rem",
            backgroundColor: "#1e293b",
            borderRadius: "0.375rem",
            fontSize: "0.85rem",
            borderLeft: dimmed
              ? "3px dashed rgba(148,163,184,0.4)"
              : "3px solid var(--accent-primary)",
          }}
        >
          <p style={{ marginBottom: "0.5rem" }}>
            <strong>Verifier Reasoning:</strong> {verdict.reasoning}
          </p>
          {verdict.error && (
            <p style={{ marginBottom: "0.5rem", color: "#fb923c" }}>
              <strong>Verifier Error Detail:</strong> {verdict.error}
            </p>
          )}
          {verdict.audit_chunk_text && (
            <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
              &quot;{verdict.audit_chunk_text}&quot;
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReportView({ report }: ReportViewProps) {
  const [expandedClaim, setExpandedClaim] = useState<string | null>(null);

  const summary = report.verification_summary;
  const sections = report.sections || [];
  const totalSurvivingClaims = sections.reduce(
    (acc, sec) => acc + (sec.claims?.length || 0),
    0
  );
  const unverifiedCount = summary?.unverified || 0;

  const toggleClaim = (id: string) =>
    setExpandedClaim((prev) => (prev === id ? null : id));

  return (
    <div className="card">
      <h2 style={{ marginBottom: "0.5rem" }}>{report.title || "Report"}</h2>
      <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", marginBottom: "1.5rem" }}>
        Query: {report.original_query}
      </p>

      {/* Case A: Every claim was stripped */}
      {totalSurvivingClaims === 0 && (
        <div
          style={{
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "0.5rem",
            padding: "1.25rem",
            marginBottom: "1.5rem",
          }}
        >
          <h4 style={{ color: "var(--danger-color)", marginBottom: "0.5rem" }}>
            No Claims Survived Fact-Checking ({summary?.stripped || 0} stripped)
          </h4>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            The cross-model verifier inspected all claims against source passages and determined that none of them met the grounding threshold.
          </p>
          {summary?.stripped_claims && summary.stripped_claims.length > 0 && (
            <details style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
              <summary style={{ cursor: "pointer", color: "var(--text-muted)" }}>
                View stripped claims ({summary.stripped_claims.length})
              </summary>
              <ul style={{ paddingLeft: "1.25rem", marginTop: "0.5rem", color: "var(--text-muted)" }}>
                {summary.stripped_claims.map((claim, idx) => (
                  <li key={idx} style={{ marginBottom: "0.25rem" }}>
                    &quot;{claim}&quot;
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Case B: Some claims stripped */}
      {totalSurvivingClaims > 0 && summary && summary.stripped_claims && summary.stripped_claims.length > 0 && (
        <div
          style={{
            backgroundColor: "rgba(234, 179, 8, 0.1)",
            border: "1px solid rgba(234, 179, 8, 0.3)",
            borderRadius: "0.5rem",
            padding: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <h4 style={{ color: "#fde047", marginBottom: "0.25rem" }}>
            Anti-Hallucination Guard active: {summary.stripped_claims.length} claim(s) removed
          </h4>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
            The cross-model verifier stripped claims that could not be grounded in retrieved source chunks.
          </p>
        </div>
      )}

      {/* Case C: Verifier errors */}
      {unverifiedCount > 0 && (
        <div
          style={{
            backgroundColor: "rgba(249, 115, 22, 0.1)",
            border: "1px solid rgba(249, 115, 22, 0.3)",
            borderRadius: "0.5rem",
            padding: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <h4 style={{ color: "#fb923c", marginBottom: "0.25rem" }}>
            ⚠️ Verifier Service Degraded: {unverifiedCount} claim(s) unverified
          </h4>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
            The cross-model verifier encountered rate limits, network timeouts, or parsing errors on these claims. Rather than stripping them, they are displayed with an &quot;UNVERIFIED&quot; badge and error details — see the grouped section below each topic.
          </p>
        </div>
      )}

      <div style={{ marginBottom: "2rem" }}>
        <h3 style={{ marginBottom: "0.5rem", color: "var(--accent-primary)" }}>Summary</h3>
        <p style={{ fontSize: "1rem", whiteSpace: "pre-line" }}>{report.intro}</p>
      </div>

      {sections.map((section, idx) => {
        // Split claims into verified (supported/partially/unsupported) and unverified
        const verifiedClaims = (section.claims || []).filter((c) => !isUnverified(c));
        const unverifiedClaims = (section.claims || []).filter((c) => isUnverified(c));
        const hasNoClaims = verifiedClaims.length === 0 && unverifiedClaims.length === 0;

        return (
          <div key={idx} style={{ marginBottom: "2rem" }}>
            <h3
              style={{
                marginBottom: "0.75rem",
                borderBottom: "1px solid var(--panel-border)",
                paddingBottom: "0.25rem",
              }}
            >
              {section.title}
            </h3>

            {hasNoClaims ? (
              <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", fontStyle: "italic", padding: "0.5rem 0" }}>
                No claims in this section survived verification.
              </p>
            ) : (
              <>
                {/* Verified claims */}
                {verifiedClaims.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {verifiedClaims.map((claim) => (
                      <ClaimCard
                        key={claim.id}
                        claim={claim}
                        expandedClaim={expandedClaim}
                        onToggle={toggleClaim}
                        dimmed={false}
                      />
                    ))}
                  </div>
                )}

                {/* Unverified claims — grouped separately with a distinct subheading */}
                {unverifiedClaims.length > 0 && (
                  <div
                    style={{
                      marginTop: verifiedClaims.length > 0 ? "1.25rem" : 0,
                      padding: "0.75rem",
                      borderRadius: "0.5rem",
                      border: "1.5px dashed rgba(148,163,184,0.25)",
                      backgroundColor: "rgba(15,23,42,0.4)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        marginBottom: "0.75rem",
                      }}
                    >
                      <span style={{ fontSize: "1rem" }}>⚠️</span>
                      <span
                        style={{
                          fontSize: "0.78rem",
                          fontWeight: 600,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          color: "var(--text-muted)",
                        }}
                      >
                        Could not be verified this run
                      </span>
                      <span
                        style={{
                          fontSize: "0.72rem",
                          color: "rgba(148,163,184,0.6)",
                          fontStyle: "italic",
                        }}
                      >
                        — verifier encountered an error; treat with caution
                      </span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                      {unverifiedClaims.map((claim) => (
                        <ClaimCard
                          key={claim.id}
                          claim={claim}
                          expandedClaim={expandedClaim}
                          onToggle={toggleClaim}
                          dimmed={true}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {section.narrative && (
              <p
                style={{
                  marginTop: "1rem",
                  fontSize: "0.95rem",
                  fontStyle: "italic",
                  color: "var(--text-muted)",
                  borderLeft: "3px solid var(--accent-primary)",
                  paddingLeft: "0.75rem",
                  lineHeight: "1.6",
                }}
              >
                {section.narrative}
              </p>
            )}
          </div>
        );
      })}

      <div style={{ marginBottom: "2rem" }}>
        <h3 style={{ marginBottom: "0.5rem", color: "var(--accent-primary)" }}>Conclusion</h3>
        <p style={{ fontSize: "1rem", whiteSpace: "pre-line" }}>{report.conclusion}</p>
      </div>

      <div>
        <h4 style={{ marginBottom: "0.5rem" }}>All Primary Sources</h4>
        <ul style={{ paddingLeft: "1.25rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>
          {report.all_sources.map((src, sidx) => (
            <li key={sidx} style={{ marginBottom: "0.25rem" }}>
              <a href={src.url} target="_blank" rel="noreferrer">
                {src.title || src.url}
              </a>{" "}
              ({src.search_provider})
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
