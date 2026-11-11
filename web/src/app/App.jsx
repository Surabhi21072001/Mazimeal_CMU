import { Suspense, lazy, useEffect, useState } from "react";

const SynergiaLightApp = lazy(() =>
  import("../features/synergia-light/SynergiaLightApp.jsx")
);
const CookPage = lazy(() => import("../features/cook/CookPage.jsx"));
const RecommendPage = lazy(() => import("../features/recommend/RecommendPage.jsx"));
const ReviewPage = lazy(() => import("../features/review/ReviewPage.jsx"));
const RecipesPage = lazy(() => import("../features/recipes/RecipesPage.jsx"));
const AdminPage = lazy(() => import("../features/admin/AdminPage.jsx"));
const NutritionReview = lazy(() => import("../features/review/NutritionReview.jsx"));

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

// Hash routing, so the screens can ship without adding a router dependency:
//   /                    the recommendations - our home page
//   #/recipes            the seed recipes, as an index
//   #/cook/<recipe_id>   the cook screen
//   #/review/nutrition   whether each recipe's numbers can be right
//   #/admin              the rules table and the queue that changes it
//   #/classic            the earlier template, which still owns signing up
//
// The root used to be that template, and it was confusing: the landing page
// was the old site and ours were reachable only if you knew the hash. Our own
// screens are the product now, so the root is the recommendations and the
// template keeps its own address.
//
// It keeps the root in one case. The confirmation email lands on
// /?confirmed=1 with no hash (see authStore.confirmRedirectUrl), and the
// template is what resumes onboarding from there, so that query string routes
// to it whatever the hash says.
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

  // Read once per render rather than kept in state: the template deletes the
  // parameter itself once it has resumed, and it does that with replaceState,
  // which fires no event this component could listen for.
  const confirming =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).has("confirmed");

  return (
    <Suspense fallback={<Loading />}>
      {hash.startsWith("#/review/nutrition") ? (
        <NutritionReview onNavigate={navigate} />
      ) : hash.startsWith("#/admin") ? (
        <AdminPage onNavigate={navigate} />
      ) : hash.startsWith("#/review") ? (
        <ReviewPage onNavigate={navigate} />
      ) : hash.startsWith("#/recipes") ? (
        <RecipesPage onNavigate={navigate} />
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
      ) : hash.startsWith("#/classic") || confirming ? (
        <SynergiaLightApp />
      ) : (
        <RecommendPage onNavigate={navigate} />
      )}
    </Suspense>
  );
}
