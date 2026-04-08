export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-border/50 ${className ?? ""}`} />;
}

export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-border bg-card p-3 flex flex-col gap-2">
      <div className="flex justify-between">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-6 w-8 rounded" />
      </div>
      <Skeleton className="h-3 w-48" />
      <div className="flex justify-between mt-1">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-2 w-16" />
      </div>
    </div>
  );
}

export function SkeletonRow() {
  return (
    <tr className="border-b border-border/50">
      <td className="px-4 py-2.5"><Skeleton className="h-4 w-24" /></td>
      <td className="px-4 py-2.5"><Skeleton className="h-4 w-28" /></td>
      <td className="px-3 py-2.5"><Skeleton className="h-4 w-10" /></td>
      <td className="px-3 py-2.5"><Skeleton className="h-6 w-8" /></td>
      <td className="hidden md:table-cell px-3 py-2.5"><Skeleton className="h-4 w-16" /></td>
      <td className="px-3 py-2.5"><Skeleton className="h-4 w-24" /></td>
      <td className="hidden md:table-cell px-3 py-2.5"><Skeleton className="h-4 w-16" /></td>
      <td className="hidden md:table-cell px-3 py-2.5"><Skeleton className="h-2 w-16" /></td>
    </tr>
  );
}

export function SkeletonReminderCard() {
  return (
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-2">
      <Skeleton className="h-4 w-36" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

export function SkeletonCallEntry() {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-3">
      <Skeleton className="h-8 w-8 rounded-lg shrink-0" />
      <div className="flex-1 flex flex-col gap-1.5">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-3 w-40" />
      </div>
    </div>
  );
}
