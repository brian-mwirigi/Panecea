"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ShieldPlus, Activity, Wifi, WifiOff, FlaskConical } from "lucide-react";
import type { DataMode } from "@/hooks/useSimulatedStream";

interface HeaderProps {
  autonomous: boolean;
  running: boolean;
  dataMode: DataMode;
}

/** Top command bar: brand, live system status and clock. */
export function Header({ autonomous, running, dataMode }: HeaderProps) {
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    const fmt = () =>
      new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    setNow(fmt());
    const id = setInterval(() => setNow(fmt()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="glass sweep relative flex flex-wrap items-center justify-between gap-4 rounded-2xl px-5 py-4"
    >
      <div className="flex items-center gap-4">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-accent/15 ring-1 ring-white/15">
          <ShieldPlus className="h-6 w-6 text-accent" strokeWidth={2} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold tracking-[0.2em] text-white">
              PANACEA
            </h1>
            <span className="rounded-md bg-white/5 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-white/50 ring-1 ring-white/10">
              v2
            </span>
          </div>
          <p className="text-xs text-white/45">
            Zero-Trust Immune System · Command Center
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <StatusPill
          label={
            dataMode === "live"
              ? "Live Backend"
              : dataMode === "fallback"
                ? "Backend Offline"
                : "Simulated"
          }
          tone={dataMode === "live" ? "good" : dataMode === "fallback" ? "warn" : "idle"}
          icon={
            dataMode === "live" ? (
              <Wifi className="h-3.5 w-3.5" />
            ) : dataMode === "fallback" ? (
              <WifiOff className="h-3.5 w-3.5" />
            ) : (
              <FlaskConical className="h-3.5 w-3.5" />
            )
          }
        />
        <StatusPill
          label={autonomous ? "Autonomous" : "Manual Override"}
          tone={autonomous ? "good" : "warn"}
        />
        <StatusPill
          label={running ? "Agent Running" : "Standby"}
          tone={running ? "active" : "idle"}
          icon={<Activity className="h-3.5 w-3.5" />}
        />
        <div className="hidden font-mono text-sm tabular-nums text-white/60 sm:block">
          {now}
        </div>
      </div>
    </motion.header>
  );
}

function StatusPill({
  label,
  tone,
  icon,
}: {
  label: string;
  tone: "good" | "warn" | "active" | "idle";
  icon?: React.ReactNode;
}) {
  const tones: Record<string, string> = {
    good: "text-accent-2",
    warn: "text-warn",
    active: "text-accent",
    idle: "text-white/40",
  };
  const dot: Record<string, string> = {
    good: "bg-accent-2 pulse-dot",
    warn: "bg-warn",
    active: "bg-accent pulse-dot",
    idle: "bg-white/30",
  };
  return (
    <div className="flex items-center gap-2 rounded-full bg-white/5 px-3 py-1.5 text-xs font-medium ring-1 ring-white/10">
      <span className={`h-2 w-2 rounded-full ${dot[tone]}`} />
      {icon && <span className={tones[tone]}>{icon}</span>}
      <span className={tones[tone]}>{label}</span>
    </div>
  );
}
