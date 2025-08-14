import vxLogo from "./assets/vx_logo.png";
import HealthBadge from "./components/HealthBadge.jsx";


export default function App() {
  return (
    <div className="p-8 text-center">
      <div className="flex justify-center">
        <img src={vxLogo} alt="VX_Rec0n" className="h-16 w-16 object-contain" />
      </div>
      <h1 className="mt-4 text-3xl font-bold tracking-tight">VX_Rec0n</h1>
      <p className="mt-2 text-gray-300">Tailwind is active if this text is styled.</p>
    </div>
  );
}

export default function App() {
  return (
    <div className="p-8 text-center space-y-4">
      {/* ...logo + heading... */}
      <HealthBadge />
    </div>
  );
}