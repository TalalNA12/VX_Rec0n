// frontend/src/store/api.js

const RAW = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const BASE = RAW.replace(/\/+$/, ""); // strip trailing slash

async function request(
  path,
  { method = "GET", headers = {}, body, signal } = {}
) {
  const r = await fetch(`${BASE}${path}`, { method, headers, body, signal });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${method} ${path} failed: ${r.status} ${text}`.trim());
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const api = {
  // expose base for components (JobWatcher report links)
  base: BASE,

  // ----- health -----
  async health({ signal } = {}) {
    try {
      return await request(`/health`, { signal });
    } catch {
      return { ok: false };
    }
  },

  // ----- targets -----
  async listTargets({ signal } = {}) {
    return request(`/api/targets`, { signal });
  },

  async getTarget(id, { signal } = {}) {
    return request(`/api/targets/${id}`, { signal });
  },

  // Optional (backend supports PUT /api/targets/{id})
  async updateTarget(id, payload, { signal } = {}) {
    return request(`/api/targets/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  },

  async createTarget(payload, { signal } = {}) {
    return request(`/api/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  },

  // Delete now always succeeds because backend cascades jobs/findings.
  // (kept signature simple; no force flag needed)
  async deleteTarget(id, { signal } = {}) {
    return request(`/api/targets/${id}`, { method: "DELETE", signal });
  },

  // ----- jobs -----
  async startScan(targetId, { signal } = {}) {
    return request(`/api/jobs/${targetId}`, { method: "POST", signal });
  },

  async jobStatus(jobId, { signal } = {}) {
    return request(`/api/jobs/${jobId}/status`, { signal });
  },

  async latestJobForTarget(targetId, { signal } = {}) {
    return request(`/api/jobs/by-target/${targetId}/latest`, { signal });
  },

  // ----- findings -----
  // ----- findings -----
// GET /api/jobs/{jobId}/findings?verified_only=true|false  (omit param for "All")
async findingsForJob(
  jobId,
  { verifiedOnly = null, cacheBust = false, signal } = {}
) {
  const params = new URLSearchParams();

  // tri-state: true | false | null/undefined (omit for "All")
  if (verifiedOnly !== null && verifiedOnly !== undefined) {
    params.set("verified_only", String(verifiedOnly)); // "true" | "false"
  }
  if (cacheBust) params.set("_", String(Date.now())); // cache-buster

  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/jobs/${jobId}/findings${qs}`, {
    headers: { "Cache-Control": "no-store", Pragma: "no-cache" },
    signal,
  });
},

  // ----- report helpers (URLs for <a href=...>) -----
  reportCsvUrl(jobId) {
    return `${BASE}/api/jobs/${jobId}/report.csv`;
  },
  reportHtmlUrl(jobId) {
    return `${BASE}/api/jobs/${jobId}/report.html`;
  },
  reportPdfUrl(jobId) {
    return `${BASE}/api/jobs/${jobId}/report.pdf`;
  },
  reportJsonUrl(jobId) {
    return `${BASE}/api/jobs/${jobId}/report.json`;
  },
};
