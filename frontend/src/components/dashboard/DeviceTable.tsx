"use client";

import { motion } from "framer-motion";
import { Cpu, Power } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";
import type { Device, DeviceStatus } from "@/lib/types";

interface DeviceTableProps {
  devices: Device[];
  onOverride: (deviceId: string) => void;
}

const STATUS_META: Record<DeviceStatus, { label: string; dot: string; text: string }> = {
  secure: { label: "Secure", dot: "bg-accent-2", text: "text-accent-2" },
  monitoring: { label: "Monitoring", dot: "bg-accent", text: "text-accent" },
  quarantined: { label: "Quarantined", dot: "bg-danger", text: "text-danger" },
  override: { label: "Overridden", dot: "bg-warn", text: "text-warn" },
};

export function DeviceTable({ devices, onOverride }: DeviceTableProps) {
  return (
    <GlassCard delay={0.2} className="flex h-full flex-col overflow-hidden">
      <PanelHeader
        title="Monitored Devices"
        subtitle={`${devices.length} medical endpoints on network`}
        icon={<Cpu className="h-4.5 w-4.5" />}
      />
      <div className="slim-scroll flex-1 overflow-x-auto px-2 pb-2">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-white/35">
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">VPC</th>
              <th className="px-3 py-2 font-medium">Ports</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">Control</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((d) => {
              const meta = STATUS_META[d.status];
              return (
                <motion.tr
                  key={d.id}
                  layout
                  className="border-t border-white/5 transition hover:bg-white/[0.03]"
                >
                  <td className="px-3 py-2.5">
                    <div className="font-medium text-white/85">{d.model}</div>
                    <div className="font-mono text-[10px] text-white/35">
                      fw {d.firmware}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-white/50">
                    {d.vpc_id}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {d.ports.map((p) => (
                        <span
                          key={p}
                          className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-white/50 ring-1 ring-white/10"
                        >
                          {p}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`flex items-center gap-1.5 text-xs ${meta.text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      onClick={() => onOverride(d.id)}
                      title="Toggle Human Override / retract policy"
                      className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-medium ring-1 transition ${
                        d.status === "override"
                          ? "bg-warn/15 text-warn ring-warn/30 hover:bg-warn/25"
                          : "bg-white/5 text-white/60 ring-white/10 hover:bg-white/10 hover:text-white/80"
                      }`}
                    >
                      <Power className="h-3 w-3" />
                      {d.status === "override" ? "Release" : "Override"}
                    </button>
                  </td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassCard>
  );
}
