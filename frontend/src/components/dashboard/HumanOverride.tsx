"use client";

import { motion } from "framer-motion";
import { UserCog, Bot } from "lucide-react";
import { GlassCard, PanelHeader } from "./GlassCard";

interface HumanOverrideProps {
  autonomous: boolean;
  onToggle: (value: boolean) => void;
}

/**
 * Global Human Override control. When autonomous mode is off, the operator
 * takes manual control and the agent stops issuing new policies automatically.
 */
export function HumanOverride({ autonomous, onToggle }: HumanOverrideProps) {
  return (
    <GlassCard delay={0.2} className="overflow-hidden">
      <PanelHeader
        title="Human Override"
        subtitle="Operator control of autonomous agent"
        icon={<UserCog className="h-4.5 w-4.5" />}
      />
      <div className="flex items-center justify-between gap-4 px-5 pb-5">
        <div className="flex items-center gap-3">
          <div
            className={`grid h-10 w-10 place-items-center rounded-xl ring-1 transition ${
              autonomous
                ? "bg-accent/15 text-accent ring-accent/30"
                : "bg-warn/15 text-warn ring-warn/30"
            }`}
          >
            {autonomous ? <Bot className="h-5 w-5" /> : <UserCog className="h-5 w-5" />}
          </div>
          <div>
            <p className="text-sm font-semibold text-white/90">
              {autonomous ? "Autonomous Mode" : "Manual Override"}
            </p>
            <p className="text-xs text-white/45">
              {autonomous
                ? "Agent enforces policies automatically"
                : "Operator approves all firewall actions"}
            </p>
          </div>
        </div>

        <button
          role="switch"
          aria-checked={autonomous}
          onClick={() => onToggle(!autonomous)}
          className={`relative h-8 w-14 shrink-0 rounded-full ring-1 transition-colors ${
            autonomous ? "bg-accent/30 ring-accent/40" : "bg-white/10 ring-white/15"
          }`}
        >
          <motion.span
            layout
            transition={{ type: "spring", stiffness: 500, damping: 32 }}
            className={`absolute top-1 h-6 w-6 rounded-full shadow-lg ${
              autonomous ? "left-7 bg-accent" : "left-1 bg-white/70"
            }`}
          />
        </button>
      </div>
    </GlassCard>
  );
}
