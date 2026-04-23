"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Home } from "lucide-react";

export default function LeaseExpiryPage() {
  const { authenticated } = useAuth();
  const router = useRouter();
  if (!authenticated) { router.replace("/"); return null; }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-mobile-nav">
      <div className="flex items-center gap-2">
        <Home size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Rentals / Lease Expiry</h1>
      </div>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted">Lease expiry tracking -- coming soon</p>
      </div>
    </div>
  );
}
