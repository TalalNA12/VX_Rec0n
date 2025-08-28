import { useEffect, useState } from "react";
import { api } from "./store/api";
import HealthBadge from "./components/HealthBadge.jsx";
import JobWatcher from "./components/JobWatcher.jsx";

/* background image behind containers */
import brandBg from "./assets/brand_bg.png";

export default function App() {
  const [targets, setTargets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [scanningId, setScanningId] = useState(null);
  const [activeJobId, setActiveJobId] = useState(null);

  const [form, setForm] = useState({
    name: "",
    base_url: "",
    is_lab_only: true,
  });

  const load = async () => {
    try {
      setLoading(true);
      setErr("");
      const data = await api.listTargets();
      setTargets(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
      setErr("Failed to load targets");
      setTargets([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.base_url) return;

    const url = form.base_url.match(/^https?:\/\//i) ? form.base_url : `http://${form.base_url}`;
    try {
      setSubmitting(true);
      await api.createTarget({ ...form, base_url: url });
      setForm({ name: "", base_url: "", is_lab_only: true });
      await load();
    } catch (e) {
      console.error(e);
      setErr("Failed to create target");
    } finally {
      setSubmitting(false);
    }
  };

  const scan = async (id) => {
    try {
      setScanningId(id);
      const res = await api.startScan(id);
      const jobId = res?.job_id ?? null;
      if (jobId) setActiveJobId(jobId);
    } catch (e) {
      console.error(e);
      alert("Failed to start scan");
    } finally {
      setScanningId(null);
    }
  };

  const viewLastJob = async (targetId) => {
    try {
      const j = await api.latestJobForTarget(targetId);
      if (j?.id) setActiveJobId(j.id);
    } catch {
      alert("No previous jobs for this target yet.");
    }
  };

  const remove = async (id) => {
    try {
      await api.deleteTarget(id);
      await load();
    } catch (e) {
      console.error(e);
      alert("Failed to delete target");
    }
  };

  return (
    <div className="relative min-h-screen p-8 text-center bg-[#0b0b0f] overflow-hidden font-body">
      {/* background brand (behind everything) */}
      <img
        src={brandBg}
        alt="Brand background"
        className="pointer-events-none select-none absolute left-1/2 -translate-x-1/2 top-1/2 -translate-y-1/2 max-w-none w-[1100px] opacity-10 blur-[1px]"
        style={{ zIndex: 0 }}
      />

      {/* Foreground */}
      <div className="relative z-10 space-y-8">
        {/* Header */}
        <div className="mt-6 mb-4 flex flex-col items-center gap-2">
          <h1 className="text-4xl font-extrabold tracking-tight neon-title">
            VX_Rec0n
          </h1>
          <p className="text-sm text-gray-400 font-body">Tailwind + FastAPI + Postgres</p>

          <div className="mt-2 flex justify-center">
            <HealthBadge />
          </div>
        </div>

        {/* Error note */}
        {err && <div className="text-red-400 text-sm">{err}</div>}

        {/* Create Target */}
        <section className="max-w-4xl mx-auto">
          <form
            onSubmit={submit}
            className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-3 items-end text-left bg-[#0b0d13]/75 backdrop-blur-md border border-[#1f2430] rounded-xl p-4 shadow-lg glass floaty"
          >
            <input
              className="px-4 py-2 text-sm sm:text-base rounded-lg bg-[#0b0d13]/70 border border-[#1f2430] text-gray-200
                         shadow-md hover:shadow-lg outline-none transition font-body"
              placeholder="Name (e.g., Juice Shop)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />

            <input
              className="px-4 py-2 text-sm sm:text-base rounded-lg bg-[#0b0d13]/70 border border-[#1f2430] text-gray-200
                         shadow-md hover:shadow-lg outline-none transition font-body"
              placeholder="http://localhost:3000"
              value={form.base_url}
              onChange={(e) => setForm({ ...form, base_url: e.target.value.trim() })}
            />

            {/* Lab only: neon toggle */}
            <label className="flex items-center gap-3 text-gray-300 px-1 py-2 select-none">
              <span className="text-sm font-body">Lab only</span>
              <span className="relative inline-flex items-center">
                <input
                  type="checkbox"
                  checked={form.is_lab_only}
                  onChange={(e) => setForm({ ...form, is_lab_only: e.target.checked })}
                  className="sr-only peer"
                />
                <span className={`toggle-track ${form.is_lab_only ? "toggle-track--on" : ""}`} />
                <span className={`toggle-knob ${form.is_lab_only ? "toggle-knob--on progress-glow" : ""}`} />
              </span>
            </label>

            <button
              className="px-4 py-2 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200
                         border border-[#2b2f3a] shadow-md hover:shadow-lg transition
                         disabled:opacity-60 btn-neon font-display"
              disabled={!form.name || !form.base_url || submitting}
              title={!form.name || !form.base_url ? "Fill name & URL" : ""}
            >
              {submitting ? "Adding…" : "Add Target"}
            </button>
          </form>
        </section>

        {/* Targets List */}
        <section className="space-y-2 max-w-4xl mx-auto">
          {loading ? (
            <div className="text-text-muted">Loading targets…</div>
          ) : targets.length ? (
            targets.map((t) => (
              <div
                key={t.id}
                className="p-4 bg-[#0b0d13]/75 backdrop-blur-md border border-[#1f2430] rounded-xl flex justify-between items-center
                           shadow-lg hover:shadow-xl transition glass"
              >
                <div className="text-left">
                  <div className="font-semibold text-gray-200 font-display tracking-wide">{t.name}</div>
                  <div className="text-sm text-gray-400 font-body">
                    {t.base_url} • {t.is_lab_only ? "LAB" : "PUBLIC"}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => scan(t.id)}
                    disabled={scanningId === t.id}
                    className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white
                               shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-100 transition
                               disabled:opacity-60 btn-neon font-display"
                  >
                    {scanningId === t.id ? "Starting…" : "Start Scan"}
                  </button>
                  <button
                    onClick={() => viewLastJob(t.id)}
                    className="px-4 py-2 rounded-lg bg-[#1f2937] hover:bg-[#374151] text-gray-200
                               border border-[#2b2f3a] shadow-md hover:shadow-lg transition btn-neon font-display"
                    title="Open the most recent job for this target"
                  >
                    View Last Job
                  </button>
                  <button
                    onClick={() => remove(t.id)}
                    className="px-4 py-2 rounded-lg bg-transparent text-gray-200
                               border border-[#2b2f3a] hover:bg-[#1f2937] transition font-body"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="text-text-muted">No targets yet. Add one above.</div>
          )}
        </section>

        {/* Job watcher modal */}
        {activeJobId && (
          <JobWatcher jobId={activeJobId} onClose={() => setActiveJobId(null)} />
        )}
      </div>
    </div>
  );
}
