// Who the screen is for.
//
// The app knows a signed-in person's diet, goal, allergies and preferences,
// and until now showed none of it: every screen addressed "Maya" from the
// bundled household whether you were signed in or not. This is the line that
// says whose numbers these are.
//
// `ingredientNames` is optional, and only the cook screen passes it. When it
// does, an allergy that appears in an ingredient's name is called out - as a
// statement about the ingredient list, not a safety verdict. It is a name
// match: "peanut" finds peanut and peanut butter, and does not find groundnut
// oil or a sauce that contains it. The wording says so, because an allergy
// warning that looks exhaustive and is not is worse than none.
import { C } from "../theme/colors";
import { useAccount } from "../services/auth/useAccount";

function Tag({ children, color = C.subtext, bg = "transparent" }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: 0.2,
        color,
        background: bg,
        border: `1px solid ${bg === "transparent" ? C.border : "transparent"}`,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

function allergyHits(allergies, ingredientNames) {
  const names = (ingredientNames || []).map((n) => String(n || "").toLowerCase());
  if (!names.length) return [];
  return (allergies || []).filter((allergy) => {
    const needle = String(allergy || "").toLowerCase().trim();
    return needle && names.some((name) => name.includes(needle));
  });
}

export default function ProfileStrip({ ingredientNames, compact = false }) {
  const { signedIn, name, profile, profileState } = useAccount();

  if (!signedIn) {
    return (
      <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
        Not signed in — these are the sample household&rsquo;s numbers. Sign in at the top right to
        see your own.
      </span>
    );
  }

  if (profileState === "loading") {
    return <span style={{ fontSize: 11.5, color: C.muted }}>Loading {name}&rsquo;s profile…</span>;
  }

  if (profileState !== "ready" || !profile) {
    return (
      <span style={{ fontSize: 11.5, color: C.muted, lineHeight: 1.6 }}>
        Signed in as {name}
        {profileState === "none"
          ? " — no profile yet, so the figures below are the sample household's."
          : " — the profile could not be loaded, so the figures below are the sample household's."}
      </span>
    );
  }

  const hits = allergyHits(profile.allergies, ingredientNames);

  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: compact ? 12.5 : 13, fontWeight: 700, color: C.navy }}>
          {profile.name}
        </span>
        {profile.diet_type ? <Tag color={C.accent} bg={C.accentLight}>{profile.diet_type}</Tag> : null}
        {profile.goal ? <Tag>{profile.goal.replace(/_/g, " ")}</Tag> : null}
        {profile.allergies?.map((allergy) => (
          <Tag key={allergy} color={C.coral} bg={C.coralLight}>
            avoids {allergy}
          </Tag>
        ))}
        {!compact
          ? profile.preferences?.slice(0, 4).map((like) => (
              <Tag key={like} color={C.sky} bg={C.skyLight}>
                likes {like}
              </Tag>
            ))
          : null}
      </div>

      {hits.length ? (
        <span style={{ fontSize: 11.5, color: C.coral, lineHeight: 1.6 }}>
          This recipe lists {hits.join(" and ")}, which {profile.name} avoids. That is a match on
          ingredient names only — it will not catch an allergen inside a sauce or under another
          name.
        </span>
      ) : null}
    </div>
  );
}
