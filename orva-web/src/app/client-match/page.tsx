"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Crosshair } from "lucide-react";

export default function ClientMatchPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  if (!authenticated) { router.replace("/"); return null; }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav">
      <div className="flex items-center gap-2">
        <Crosshair size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Client Match</h1>
      </div>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted">Owner-client matching -- coming soon</p>
      </div>
    </div>
  );
}
