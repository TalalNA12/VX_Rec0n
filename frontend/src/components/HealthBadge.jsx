// frontend/src/components/HealthBadge.jsx
import { useEffect, useMemo, useRef, useState } from "react";

const raw = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const API = raw.replace(/\/+$/, ""); // strip trailing slash safely

export default function HealthBadge() {
  const [ok, setOk] = useState(null); // null = checking, true/false afterwards
  const [ms, setMs] = useState(null); // latency
  const [err, setErr] = useState(""); // last error
  const timerRef = useRef(null);

  const checkHealth = useMemo(() => {
    return async () => {
      setErr("");
      setMs(null);
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort("timeout"), 5000);
      const t0 = performance.now();
      try {
        const res = await fetch(`${API}/health`, { signal: ctrl.signal });
        const json = await res.json().catch(() => ({}));
        const t1 = performance.now();
        setMs(Math.max(0, Math.round(t1 - t0)));
        setOk(Boolean(json?.ok) && res.ok);
        if (!res.ok) setErr(`HTTP ${res.status}`);
      } catch (e) {
        const t1 = performance.now();
        setMs(Math.max(0, Math.round(t1 - t0)));
        setOk(false);
        setErr(String(e?.message || e));
      } finally {
        clearTimeout(t);
      }
    };
  }, []);

  useEffect(() => {
    checkHealth();
    timerRef.current = setInterval(checkHealth, 10000);
    return () => clearInterval(timerRef.current);
  }, [checkHealth]);

  const statusDot = () => {
    if (ok === null) return "bg-gray-400 animate-pulse"; // checking
    if (ok) return "bg-green-400 shadow-[0_0_8px_#34d399]";
    return "bg-red-500 shadow-[0_0_8px_#ef4444]";
  };

  const text =
    ok === null ? "Checking…" : ok ? "Backend: OK" : "Backend: Down";

  return (
    <div className="inline-flex items-center gap-3 px-3 py-1.5 rounded-lg glass text-sm text-gray-300">
      {/* Status Dot */}
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${statusDot()}`} />
      {/* Status Text */}
      <span className="font-medium">{text}</span>
      {ms !== null && (
        <span className="text-xs text-gray-400">({ms} ms)</span>
      )}
      {/* Retry Button */}
      {ok === false && (
        <button
          onClick={checkHealth}
          className="ml-2 text-xs px-2 py-0.5 rounded bg-[#1f2937] hover:bg-[#374151] border border-[#2b2f3a] btn-neon"
          title={err || "Retry health check"}
        >
          Retry
        </button>
      )}
    </div>
  );
}
