import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function HealthBadge() {
  const [ok, setOk] = useState(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => r.json())
      .then(d => setOk(Boolean(d?.ok)))
      .catch(() => setOk(false));
  }, []);

  const color = ok === null ? "bg-gray-500" : ok ? "bg-green-500" : "bg-red-500";
  const text  = ok === null ? "Checking..." : ok ? "Backend: OK" : "Backend: Down";

  return (
    <div className="inline-flex items-center gap-2 text-sm text-gray-300">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
      {text}
    </div>
  );
}
