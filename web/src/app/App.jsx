import { Suspense, lazy } from "react";

const SynergiaLightApp = lazy(() =>
  import("../features/synergia-light/SynergiaLightApp.jsx")
);

export default function App() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#f5f1e8",
            color: "#163127",
            fontFamily: "Plus Jakarta Sans, sans-serif",
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          Loading Mazimeal...
        </div>
      }
    >
      <SynergiaLightApp />
    </Suspense>
  );
}
