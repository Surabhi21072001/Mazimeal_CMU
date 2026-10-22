import { Suspense, lazy, useEffect, useState } from "react";

const SynergiaLightApp = lazy(() =>
  import("../features/synergia-light/SynergiaLightApp.jsx")
);
const CookPage = lazy(() => import("../features/cook/CookPage.jsx"));
const RecommendPage = lazy(() => import("../features/recommend/RecommendPage.jsx"));
const ReviewPage = lazy(() => import("../features/review/ReviewPage.jsx"));

function Loading() {
  return (
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
  );
}

// Hash routing, so the new screens can ship without touching the existing app
// or adding a router dependency:
//   #/cook/<recipe_id>   the cook screen
//   anything else        the app as it was
function useHashRoute() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHashRoute();
  const navigate = (next) => {
    window.location.hash = next;
  };

  // #/cook/<recipe_id>?n=<nutrient> - the nutrient is optional and only tells
  // the page which one to headline; it picks the best one on its own otherwise.
  const cookMatch = hash.match(/^#\/cook(?:\/([\w-]+))?(?:\?(.*))?$/);
  const focusNutrient = cookMatch?.[2] ? new URLSearchParams(cookMatch[2]).get("n") : null;

  return (
    <Suspense fallback={<Loading />}>
      {hash.startsWith("#/review") ? (
        <ReviewPage onNavigate={navigate} />
      ) : hash.startsWith("#/recommend") ? (
        <RecommendPage onNavigate={navigate} />
      ) : cookMatch ? (
        // keyed so switching recipes remounts with fresh state instead of
        // resetting it inside an effect
        <CookPage
          key={cookMatch[1] || "falafel-001"}
          recipeId={cookMatch[1] || "falafel-001"}
          focusNutrient={focusNutrient}
          onNavigate={navigate}
        />
      ) : (
        <SynergiaLightApp />
      )}
    </Suspense>
  );
}
