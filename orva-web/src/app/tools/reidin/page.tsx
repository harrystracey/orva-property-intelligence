"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Wrench } from "lucide-react";

export default function ReidinPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  if (!authenticated) { router.replace("/"); return null; }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      <div className="flex items-center gap-2">
        <Wrench size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Reidin Sync</h1>
      </div>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted">Reidin data sync -- coming soon</p>
      </div>
    </div>
  );
}
