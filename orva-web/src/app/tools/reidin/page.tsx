"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { LoginForm } from "@/components/login-form";
import {
  getReidinStatus,
  uploadReidinCSV,
  ReidinStatus,
  ReidinUploadResult,
} from "@/lib/api";
import {
  Wrench,
  Upload,
  FileSpreadsheet,
  Database,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Info,
} from "lucide-react";

export default function ReidinPage() {
  const { authenticated } = useAuth();
  const [status, setStatus] = useState<ReidinStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataType, setDataType] = useState<"sales" | "rentals">("sales");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ReidinUploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getReidinStatus();
      setStatus(s);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setError(null);
    setResult(null);
    try {
      const r = await uploadReidinCSV(selectedFile, dataType);
      setResult(r);
      setSelectedFile(null);
      if (fileRef.current) fileRef.current.value = "";
      refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file?.name.toLowerCase().endsWith(".csv")) {
      setSelectedFile(file);
      setResult(null);
      setError(null);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setResult(null);
      setError(null);
    }
  };

  if (!authenticated) return <LoginForm />;

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pb-20 md:pb-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Wrench size={20} className="text-accent" />
        <h1 className="text-lg font-semibold text-foreground">Reidin Sync</h1>
      </div>

      {/* Info Banner */}
      <div className="flex items-start gap-2 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3 text-sm text-muted">
        <Info size={16} className="mt-0.5 shrink-0 text-accent" />
        <span>
          Upload Reidin CSV exports to enrich lead data with DLD transaction
          records. Sales data feeds bedroom/size at Priority 1.5. Rental data
          provides market rent intelligence.
        </span>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatusCard
          label="Sales Data"
          icon={<Database size={18} />}
          info={status?.sales}
          loading={loading}
        />
        <StatusCard
          label="Rental Data"
          icon={<FileSpreadsheet size={18} />}
          info={status?.rentals}
          loading={loading}
        />
      </div>

      {/* Upload Section */}
      <div className="rounded-lg border border-border bg-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">
          Upload Reidin CSV
        </h2>

        {/* Data Type Toggle */}
        <div className="mb-4 flex gap-2">
          {(["sales", "rentals"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setDataType(t)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                dataType === t
                  ? "bg-accent text-white"
                  : "bg-muted/10 text-muted hover:bg-muted/20"
              }`}
            >
              {t === "sales" ? "Sales Transactions" : "Rental Contracts"}
            </button>
          ))}
        </div>

        {/* Drop Zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
            dragOver
              ? "border-accent bg-accent/5"
              : selectedFile
                ? "border-accent/40 bg-accent/5"
                : "border-border hover:border-accent/30"
          }`}
        >
          <Upload
            size={24}
            className={selectedFile ? "text-accent" : "text-muted"}
          />
          {selectedFile ? (
            <div>
              <p className="text-sm font-medium text-foreground">
                {selectedFile.name}
              </p>
              <p className="text-xs text-muted">
                {(selectedFile.size / 1024).toFixed(0)} KB — click to change
              </p>
            </div>
          ) : (
            <div>
              <p className="text-sm text-muted">
                Drop a CSV file here or click to browse
              </p>
              <p className="text-xs text-muted/60">
                Reidin export with columns: Project, Unit No, Bedrooms, Size,
                Date, Amount
              </p>
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
            className="hidden"
          />
        </div>

        {/* Upload Button */}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
            className="flex items-center gap-2 rounded-md bg-accent px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {uploading ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Upload size={16} />
            )}
            {uploading ? "Processing..." : "Process & Upload"}
          </button>
          {selectedFile && !uploading && (
            <button
              onClick={() => {
                setSelectedFile(null);
                if (fileRef.current) fileRef.current.value = "";
              }}
              className="text-xs text-muted hover:text-foreground"
            >
              Clear
            </button>
          )}
        </div>

        {/* Result */}
        {result && (
          <div className="mt-4 rounded-lg border border-green-500/20 bg-green-500/5 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-green-400">
              <CheckCircle2 size={16} />
              Processed successfully
            </div>
            <div className="mt-2 grid grid-cols-3 gap-4 text-xs text-muted">
              <div>
                <span className="text-foreground font-medium">
                  {result.rows_in.toLocaleString()}
                </span>{" "}
                rows in
              </div>
              <div>
                <span className="text-foreground font-medium">
                  {result.rows_out.toLocaleString()}
                </span>{" "}
                units saved
              </div>
              <div>
                <span className="text-foreground font-medium">
                  {result.buildings}
                </span>{" "}
                buildings
              </div>
            </div>
            {result.warnings.length > 0 && (
              <div className="mt-3 space-y-1">
                {result.warnings.map((w, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-1.5 text-xs text-yellow-400"
                  >
                    <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                    {w}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400">
            <XCircle size={16} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Status Card ─────────────────────────────────────────────────── */

function StatusCard({
  label,
  icon,
  info,
  loading,
}: {
  label: string;
  icon: React.ReactNode;
  info?: { exists: boolean; rows: number; buildings: number; last_modified: string | null } | null;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-muted">
        {icon}
        {label}
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted/60">
          <RefreshCw size={12} className="animate-spin" /> Loading...
        </div>
      ) : info?.exists ? (
        <div className="space-y-1 text-xs">
          <div className="text-foreground">
            <span className="text-lg font-semibold">
              {info.rows.toLocaleString()}
            </span>{" "}
            <span className="text-muted">
              units across {info.buildings} buildings
            </span>
          </div>
          {info.last_modified && (
            <div className="text-muted/60">
              Updated{" "}
              {new Date(info.last_modified).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-xs text-muted/60">
          <XCircle size={12} /> Not available
        </div>
      )}
    </div>
  );
}
