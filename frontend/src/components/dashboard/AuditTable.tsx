"use client";

import { motion } from "framer-motion";
import { ScrollText, RefreshCw, ShieldAlert } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";
import type { AuditEntry } from "@/lib/types";

interface AuditTableProps {
  entries: AuditEntry[];
  loading: boolean;
  onRefresh: () => void;
}

function fmtTime(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function hasRealCve(cve?: string): cve is string {
  return !!cve && /^CVE-/i.test(cve.trim());
}

/** Real append-only decision history from GET /api/v1/agent/audit. */
export function AuditTable({ entries, loading, onRefresh }: AuditTableProps) {
  return (
    <GlassCard delay={0.1} className="flex h-full flex-col overflow-hidden">
      <PanelHeader
        title="Decision Audit Trail"
        subtitle="rest · /agent/audit"
        icon={<ScrollText className="h-4 w-4" />}
        action={
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-1.5 text-xs font-medium text-muted ring-1 ring-hairline transition hover:text-foreground disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        }
      />
      <div className="slim-scroll flex-1 overflow-auto px-2 pb-2">
        {entries.length === 0 ? (
          <div className="flex h-full min-h-48 flex-col items-center justify-center text-center">
            <ScrollText className="h-6 w-6 text-faint" />
            <p className="mt-3 text-sm text-muted">
              {loading ? "Loading audit log…" : "No recorded decisions yet"}
            </p>
            <p className="section-label mt-1">Every real agent decision is logged here</p>
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left">
                <th className="section-label px-3 py-2.5">Time</th>
                <th className="section-label px-3 py-2.5">Device</th>
                <th className="section-label px-3 py-2.5">Confidence</th>
                <th className="section-label px-3 py-2.5">CVE</th>
                <th className="section-label px-3 py-2.5">Rules</th>
                <th className="section-label px-3 py-2.5">Drift</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <motion.tr
                  key={`${e.lease_id ?? "entry"}-${i}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="border-t border-hairline align-top transition hover:bg-surface-2"
                >
                  <td className="px-3 py-2.5 font-mono text-[11px] text-muted">{fmtTime(e.timestamp)}</td>
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-foreground">{e.device_model ?? "—"}</div>
                    <div className="font-mono text-[10px] text-faint">
                      {e.firmware_version ? `fw ${e.firmware_version}` : e.operator_id ?? ""}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    {typeof e.confidence_score === "number" ? (
                      <span
                        className={`font-mono text-sm ${
                          e.confidence_score >= 90
                            ? "text-accent-2"
                            : e.confidence_score >= 70
                              ? "text-accent"
                              : "text-warn"
                        }`}
                      >
                        {e.confidence_score}%
                      </span>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {hasRealCve(e.cve_flagged) ? (
                      <span className="inline-flex items-center gap-1 rounded bg-danger/10 px-1.5 py-0.5 font-mono text-[10px] text-danger ring-1 ring-danger/25">
                        <ShieldAlert className="h-3 w-3" />
                        {e.cve_flagged}
                      </span>
                    ) : (
                      <span className="text-faint">none</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {(e.firewall_rules ?? []).map((r, j) => (
                        <span
                          key={`${r.port}-${j}`}
                          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ring-1 ${
                            r.action === "ALLOW"
                              ? "bg-accent-2/10 text-accent-2 ring-accent-2/25"
                              : "bg-danger/10 text-danger ring-danger/25"
                          }`}
                        >
                          {r.port} {r.action === "ALLOW" ? "OPEN" : "BLOCK"}
                        </span>
                      ))}
                      {!(e.firewall_rules ?? []).length && <span className="text-faint">—</span>}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-[11px] text-muted">
                    {e.drift_alert ? (
                      <span className="text-warn">{e.drift_alert}</span>
                    ) : (
                      <span className="text-faint">stable</span>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </GlassCard>
  );
}
