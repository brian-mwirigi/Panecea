"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { TerminalSquare, Play, Loader2 } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";
import type { AgentLogLine, LogLevel } from "@/lib/types";

interface AgentTerminalProps {
  logs: AgentLogLine[];
  running: boolean;
  onRun: () => void;
}

const LEVEL_STYLE: Record<LogLevel, { color: string; tag: string }> = {
  info: { color: "text-white/70", tag: "text-accent" },
  success: { color: "text-accent-2", tag: "text-accent-2" },
  warn: { color: "text-warn", tag: "text-warn" },
  threat: { color: "text-danger", tag: "text-danger" },
  system: { color: "text-accent-3", tag: "text-accent-3" },
};

export function AgentTerminal({ logs, running, onRun }: AgentTerminalProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <GlassCard delay={0.1} className="flex h-full flex-col overflow-hidden">
      <PanelHeader
        title="Agent Reasoning Stream"
        subtitle="WebSocket · /ws/agent-stream"
        icon={<TerminalSquare className="h-4.5 w-4.5" />}
        action={
          <button
            onClick={onRun}
            disabled={running}
            className="flex items-center gap-1.5 rounded-lg bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent ring-1 ring-accent/30 transition hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Running
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" /> Run Agent
              </>
            )}
          </button>
        }
      />
      <div
        ref={scrollRef}
        className="slim-scroll relative m-3 mt-0 flex-1 overflow-y-auto rounded-xl bg-black/40 p-3 font-mono text-[12px] leading-relaxed ring-1 ring-white/5"
      >
        <AnimatePresence initial={false}>
          {logs.map((line) => {
            const style = LEVEL_STYLE[line.level];
            return (
              <motion.div
                key={line.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.22 }}
                className="flex gap-2 py-0.5"
              >
                <span className="shrink-0 text-white/25">
                  {new Date(line.ts).toLocaleTimeString([], {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                {line.step != null && (
                  <span className={`shrink-0 font-semibold ${style.tag}`}>
                    [{line.step}]
                  </span>
                )}
                <span className={style.color}>{line.text}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {running && (
          <div className="flex items-center gap-2 py-0.5 text-white/40">
            <span className="inline-block h-3 w-1.5 animate-pulse bg-accent" />
          </div>
        )}
      </div>
    </GlassCard>
  );
}
