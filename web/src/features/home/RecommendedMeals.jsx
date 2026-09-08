import { useState } from "react";
import { C } from "../../shared/theme/colors";
import { MEAL_SLOTS, nutrientLabel, reasonSentence, tagLabel } from "./homeData";

const NAVY = "#163F77";
const SLOT_ICON = { Breakfast: "🌅", Lunch: "🥗", Dinner: "🍽️", Snack: "🍎" };
const MEMBER_COLORS = ["#2F6A4F", "#3D86D9", "#F09B1C", "#7D6BA8", "#C55B4A"];

function ScoreBar({ label, value, color }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div style={{ display: "grid", gridTemplateColumns: "44px 1fr 34px", gap: 8, alignItems: "center", fontSize: 12 }}>
      <span style={{ color: "#4A607A", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      <div style={{ height: 6, borderRadius: 4, background: "#E8EDF3", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4 }} />
      </div>
      <span style={{ color: "#60718B", fontWeight: 700, textAlign: "right" }}>{Math.round(pct)}</span>
    </div>
  );
}

function PickCard({ pick, members, featured, onSelect }) {
  const time = (pick.prep_min || 0) + (pick.cook_min || 0);
  const meta = [pick.calories ? `${pick.calories} kcal` : null, time ? `${time} min` : null].filter(Boolean).join(" · ");
  return (
    <button
      type="button"
      onClick={() => onSelect?.(pick)}
      style={{
        textAlign: "left",
        display: "grid",
        gap: 8,
        padding: featured ? "14px 14px 12px" : "10px 12px",
        borderRadius: 14,
        border: `1px solid ${featured ? "#CFE0D5" : C.border}`,
        background: featured ? "linear-gradient(180deg, #F3FAF5, #FFFFFF)" : "rgba(255,255,255,0.9)",
        cursor: onSelect ? "pointer" : "default",
        font: "inherit",
        color: "inherit",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
        <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: featured ? 17 : 14, color: NAVY, lineHeight: 1.2 }}>{pick.name}</div>
        <div style={{ fontSize: 13, fontWeight: 800, color: C.accent, whiteSpace: "nowrap" }}>{Math.round(pick.min_score)}</div>
      </div>
      {meta && <div style={{ fontSize: 12, color: "#60718B", fontWeight: 600 }}>{meta}</div>}
      {featured && (
        <>
          <div style={{ fontSize: 13, color: "#284468", lineHeight: 1.5 }}>{reasonSentence(pick)}</div>
          <div style={{ display: "grid", gap: 4 }}>
            {members.map((m, i) => (
              <ScoreBar key={m.name} label={m.name} value={pick.per_member?.[m.name]} color={MEMBER_COLORS[i % MEMBER_COLORS.length]} />
            ))}
          </div>
          {pick.tags?.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {pick.tags.map((t) => (
                <span key={t} style={{ fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: C.accentLight, color: C.accentDark }}>
                  {tagLabel(t)}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </button>
  );
}

export default function RecommendedMeals({ home, loading, onSelectRecipe }) {
  const [showBlocked, setShowBlocked] = useState(false);
  const members = home?.members || [];
  const picks = home?.picks || {};
  const blocked = home?.blocked || [];
  const live = home?.source === "live";

  return (
    <div className="card" style={{ padding: "24px 24px 20px", display: "grid", gap: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <div style={{ color: C.accent, fontSize: 13, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase" }}>
            Recommended for {home?.household?.name || "your household"}
          </div>
          <div style={{ fontFamily: "'Lora'", fontWeight: 700, fontSize: 26, color: NAVY, marginTop: 4 }}>
            What fills today's gaps
          </div>
        </div>
        <span
          title={live ? "Scored live from the database" : "Sample output. Connect Supabase to score live."}
          style={{ fontSize: 12, fontWeight: 700, padding: "5px 10px", borderRadius: 999, background: live ? C.accentLight : "#FFF4D9", color: live ? C.accentDark : "#8E5B26" }}
        >
          {live ? "Live" : "Sample data"}
        </span>
      </div>

      {members.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {members.map((m, i) => {
            const open = (m.gaps || []).filter((g) => g.pct_open >= 50).slice(0, 3);
            return (
              <div key={m.name} style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 12px", borderRadius: 12, background: "rgba(255,255,255,0.9)", border: `1px solid ${C.border}`, fontSize: 13 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: MEMBER_COLORS[i % MEMBER_COLORS.length] }} />
                <span style={{ fontWeight: 800, color: NAVY }}>{m.name}</span>
                <span style={{ color: "#4A607A" }}>
                  {open.length ? `still needs ${open.map((g) => nutrientLabel(g.nutrient)).join(", ")}` : "on track today"}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {loading ? (
        <div style={{ color: "#60718B", fontWeight: 600, padding: "20px 0" }}>Scoring recipes for your household…</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
          {MEAL_SLOTS.map((slot) => {
            const list = picks[slot] || [];
            return (
              <div key={slot} style={{ display: "grid", gap: 8, alignContent: "start" }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#4A607A", letterSpacing: 0.6, textTransform: "uppercase" }}>
                  {SLOT_ICON[slot]} {slot}
                </div>
                {list.length === 0 && <div style={{ fontSize: 13, color: "#8A97A8" }}>Nothing fits this slot yet.</div>}
                {list.map((pick, i) => (
                  <PickCard key={pick.recipe_id} pick={pick} members={members} featured={i === 0} onSelect={onSelectRecipe} />
                ))}
              </div>
            );
          })}
        </div>
      )}

      {blocked.length > 0 && (
        <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
          <button
            type="button"
            onClick={() => setShowBlocked((v) => !v)}
            style={{ background: "none", border: "none", padding: 0, font: "inherit", fontSize: 13, fontWeight: 700, color: "#8E5B26", cursor: "pointer" }}
          >
            {showBlocked ? "▾" : "▸"} {blocked.length} recipe{blocked.length === 1 ? "" : "s"} hidden for this household
          </button>
          {showBlocked && (
            <div style={{ display: "grid", gap: 4, marginTop: 8, fontSize: 13, color: "#4A607A" }}>
              {blocked.map((b) => (
                <div key={b.recipe_id}>
                  <span style={{ fontWeight: 700, color: NAVY }}>{b.name}</span> · {b.reason}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
