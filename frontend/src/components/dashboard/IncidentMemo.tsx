"use client";

import { AnimatePresence, motion } from "framer-motion";
import { FileText, ShieldAlert, CheckCircle2, XCircle } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";
import type { IncidentMemo as IncidentMemoType } from "@/lib/types";

interface IncidentMemoProps {
  memos: IncidentMemoType[];
}

export function IncidentMemo({ memos }: IncidentMemoProps) {
  return (
    <GlassCard delay={0.15} className="flex h-full flex-col overflow-hidden">
      <PanelHeader
        title="Incident Memos"
        subtitle="Contract B · agent decisions"
        icon={<FileText className="h-4.5 w-4.5" />}
      />
      <div className="slim-scroll flex-1 space-y-3 overflow-y-auto px-4 pb-4">
        <AnimatePresence initial={false}>
          {memos.map((memo) => (
            <MemoCard key={memo.id} memo={memo} />
          ))}
        </AnimatePresence>
      </div>
    </GlassCard>
  );
}

function MemoCard({ memo }: { memo: IncidentMemoType }) {
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: -10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl bg-white/[0.03] p-3.5 ring-1 ring-white/10"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white/90">
              {memo.device_model}
            </span>
            <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-white/45 ring-1 ring-white/10">
              {memo.target_vpc_id}
            </span>
          </div>
          <span className="text-[11px] text-white/35">
            {new Date(memo.created_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
        <ConfidenceGauge score={memo.confidence_score} />
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {memo.firewall_rules.map((rule, i) => (
          <span
            key={`${rule.port}-${i}`}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[11px] ring-1 ${
              rule.action === "ALLOW"
                ? "bg-accent-2/10 text-accent-2 ring-accent-2/25"
                : "bg-danger/10 text-danger ring-danger/25"
            }`}
          >
            {rule.action === "ALLOW" ? (
              <CheckCircle2 className="h-3 w-3" />
            ) : (
              <XCircle className="h-3 w-3" />
            )}
            {rule.action} · {rule.port}
          </span>
        ))}
      </div>

      <p className="mt-3 text-[12px] leading-relaxed text-white/55">{memo.memo_text}</p>

      {memo.cve_flagged && (
        <div className="mt-2.5 flex items-center gap-1.5 rounded-md bg-danger/10 px-2 py-1 text-[11px] font-medium text-danger ring-1 ring-danger/20">
          <ShieldAlert className="h-3.5 w-3.5" />
          {memo.cve_flagged}
        </div>
      )}
    </motion.article>
  );
}

function ConfidenceGauge({ score }: { score: number }) {
  const tone = score >= 95 ? "#34d399" : score >= 90 ? "#22d3ee" : "#fbbf24";
  const r = 16;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  return (
    <div className="relative grid h-12 w-12 shrink-0 place-items-center">
      <svg viewBox="0 0 40 40" className="h-12 w-12 -rotate-90">
        <circle cx="20" cy="20" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <span className="absolute font-mono text-[11px] font-semibold text-white/85">
        {score}
      </span>
    </div>
  );
}
