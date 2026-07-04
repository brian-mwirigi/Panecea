"use client";

import { motion } from "framer-motion";
import {
  ShieldCheck,
  Waypoints,
  Ban,
  Gauge,
  Network,
  type LucideIcon,
} from "lucide-react";
import { GlassCard } from "./GlassCard";
import type { DashboardStats } from "@/lib/types";

interface StatDef {
  key: keyof DashboardStats;
  label: string;
  icon: LucideIcon;
  suffix?: string;
}

const STATS: StatDef[] = [
  { key: "devicesProtected", label: "Devices Protected", icon: ShieldCheck },
  { key: "activeRules", label: "Active Firewall Rules", icon: Waypoints },
  { key: "threatsBlocked", label: "Threats Blocked · 24h", icon: Ban },
  { key: "avgConfidence", label: "Avg Confidence", icon: Gauge, suffix: "%" },
  { key: "portsMonitored", label: "Ports Monitored", icon: Network },
];

export function StatsRow({ stats }: { stats: DashboardStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {STATS.map((def, i) => {
        const Icon = def.icon;
        return (
          <GlassCard key={def.key} interactive delay={0.05 * i} className="p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-white/45">{def.label}</span>
              <Icon className="h-4 w-4 text-white/35" />
            </div>
            <div className="mt-3 flex items-end gap-1">
              <AnimatedNumber value={stats[def.key]} />
              {def.suffix && (
                <span className="pb-1 text-sm font-medium text-white/40">{def.suffix}</span>
              )}
            </div>
          </GlassCard>
        );
      })}
    </div>
  );
}

/** Simple count-up on value change. */
function AnimatedNumber({ value }: { value: number }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0.4, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="font-mono text-2xl font-semibold tabular-nums text-white"
    >
      {value}
    </motion.span>
  );
}
