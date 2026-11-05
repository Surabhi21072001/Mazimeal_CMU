// Reviewing the numbers, not the words.
//
// The other review screen asks whether the suggestion text is good. This one
// asks whether a recipe's nutrition can be right at all, which is a question
// nobody has answered for any of the fifty.
//
// There is exactly one measurement available. Food.com publishes energy and we
// can also compute it from ingredient weights, so their ratio says how far off
// the computation is. Every nutrient that exists only by computation - iron,
// calcium, zinc, folate, vitamin C, which is to say the ones the rules are
// about - carries the same error with no published figure to catch it. So the
// list is ordered by that ratio: the recipe furthest from 1.00 is the one worth
// opening, and a list in spreadsheet order buries it.
//
// A verdict is a person's judgement, and the three on offer are deliberately
// not two. "Needs data" is the honest answer when the quantities are too
// damaged to judge, and collapsing it into "implausible" would send the data
// team to re-check a recipe whose real problem is that nothing can be checked.
import { useCallback, useEffect, useState } from "react";
import { C } from "../../shared/theme/colors";
import { getSession } from "../../shared/services/auth/authStore";
import { nutritionQueue, recordNutritionVerdict } from "../../shared/services/api/review";
import { Card, Chip } from "../cook/bits";

const VERDICTS = [
  {
    id: "plausible",
    label: "Plausible",
    tone: C.accent,
    hint: "The numbers could be right for this dish.",
  },
  {
    id: "implausible",
    label: "Implausible",
    tone: C.coral,
    hint: "Something is wrong and you can say what.",
  },
  {
    id: "needs_data",
    label: "Needs data",
    tone: C.gold,
    hint: "Cannot be judged until the quantities are reviewed.",
  },
];

// Within 15% is as close as this pipeline gets on the recipes that are right;
// past 2x the quantities are not describing the same dish.
function ratioTone(ratio) {
  if (ratio == null) return C.muted;
  const off = Math.abs(ratio - 1);
  if (off <= 0.15) return C.accent;
  if (ratio >= 2 || ratio <= 0.5) return C.coral;
  return C.gold;
}

function Row({ item, busy, onVerdict }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);
  const review = item.review;
  const tone = ratioTone(item.energy_ratio);

  const submit = async (verdict) => {
    setError(null);
    if (verdict !== "plausible" && !reason.trim()) {
      setError("Say what is wrong — a verdict without a reason is not actionable.");
      return;
    }
    try {
      await onVerdict(item.recipe_id, verdict, reason.trim() || null);
      setReason("");
      setOpen(false);
    } catch (err) {
      setError(err.status === 401 ? "Sign in on the admin screen first." : err.message);
    }
  };

  return (
    <Card style={{ padding: 14, display: "grid", gap: 10 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        <span
          style={{
            fontSize: 15,
            fontWeight: 700,
            color: tone,
            fontVariantNumeric: "tabular-nums",
            minWidth: 58,
          }}
          title="Computed energy divided by the figure Food.com publishes"
        >
          {item.energy_ratio == null ? "—" : `${item.energy_ratio.toFixed(2)}x`}
        </span>
        <a
          href={`#/cook/${item.recipe_id}`}
          style={{ flex: 1, fontSize: 13.5, color: C.text, minWidth: 160, textDecoration: "none" }}
        >
          {item.name}
        </a>
        {review ? (
          <Chip
            color={VERDICTS.find((v) => v.id === review.verdict)?.tone || C.subtext}
            border={C.border}
            title={`${review.reviewer} · ${review.reviewed_at}`}
          >
            {review.verdict.replace("_", " ")}
            {review.stale ? " · stale" : ""}
          </Chip>
        ) : (
          <Chip color={C.muted} border={C.border}>unreviewed</Chip>
        )}
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11, color: C.muted }}>
        <span>published {item.energy_published ?? "—"} kcal</span>
        <span>computed {item.energy_derived ?? "—"} kcal</span>
        <span>{item.servings} servings</span>
        <span style={{ color: item.lines_misaligned ? C.coral : C.muted }}>
          {item.lines_misaligned} of {item.lines} lines may have the wrong quantity
        </span>
        {item.grams_guessed ? <span style={{ color: C.gold }}>{item.grams_guessed} guessed weights</span> : null}
        {item.lines_without_nutrition ? (
          <span style={{ color: C.coral }}>{item.lines_without_nutrition} with no nutrition data</span>
        ) : null}
      </div>

      {review?.reason ? (
        <span style={{ fontSize: 12, color: C.subtext, lineHeight: 1.6 }}>
          “{review.reason}” — {review.reviewer}
          {review.stale
            ? ` (judged at ${review.energy_ratio?.toFixed(2)}x; the data has changed since)`
            : ""}
        </span>
      ) : null}

      {open ? (
        <div style={{ display: "grid", gap: 8 }}>
          <textarea
            value={reason}
            rows={2}
            placeholder="What is wrong, or what is missing?"
            onChange={(event) => setReason(event.target.value)}
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "8px 10px",
              borderRadius: 9,
              border: `1px solid ${C.border}`,
              background: C.white,
              color: C.text,
              fontSize: 12.5,
              fontFamily: "inherit",
              resize: "vertical",
            }}
          />
          {error ? <span style={{ fontSize: 11.5, color: C.coral }}>{error}</span> : null}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {VERDICTS.map((verdict) => (
              <button
                key={verdict.id}
                type="button"
                disabled={busy}
                title={verdict.hint}
                onClick={() => submit(verdict.id)}
                style={{
                  padding: "6px 12px",
                  borderRadius: 9,
                  border: `1px solid ${verdict.tone}`,
                  background: C.white,
                  color: verdict.tone,
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: busy ? "default" : "pointer",
                  fontFamily: "inherit",
                }}
              >
                {verdict.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{
                border: "none",
                background: "transparent",
                color: C.muted,
                fontSize: 11.5,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          style={{
            justifySelf: "start",
            padding: "5px 11px",
            borderRadius: 9,
            border: `1px solid ${C.border}`,
            background: C.white,
            color: C.navy,
            fontSize: 11.5,
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          {review ? "Review again" : "Review the numbers"}
        </button>
      )}
    </Card>
  );
}

export default function NutritionReview({ onNavigate }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    let live = true;
    nutritionQueue()
      .then((data) => live && setPayload(data))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [tick]);

  useEffect(() => {
    let live = true;
    getSession().then((session) => live && setSignedIn(Boolean(session)));
    return () => {
      live = false;
    };
  }, []);

  const onVerdict = useCallback(async (recipeId, verdict, reason) => {
    setBusy(true);
    try {
      await recordNutritionVerdict(recipeId, verdict, reason);
      setTick((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }, []);

  const items = (payload?.items || []).filter((item) => {
    if (filter === "unreviewed") return !item.review;
    if (filter === "reviewed") return Boolean(item.review);
    if (filter === "worst") return item.energy_ratio != null && Math.abs(item.energy_ratio - 1) > 0.5;
    return true;
  });

  return (
    <div style={{ minHeight: "100vh", background: C.bg, paddingBottom: 48 }}>
      <header
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: "12px 20px",
          display: "flex",
          alignItems: "center",
          gap: 14,
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={() => onNavigate("#/review")}
          style={{ border: "none", background: "transparent", padding: 0, cursor: "pointer", display: "grid", justifyItems: "start" }}
        >
          <span style={{ fontFamily: "Fraunces, serif", fontSize: 18, fontWeight: 700, color: C.accent }}>
            MaziMeal
          </span>
          <span style={{ fontSize: 10.5, color: C.muted }}>← Review the text instead</span>
        </button>
        <span style={{ flex: 1 }} />
        {!signedIn ? (
          <Chip color={C.gold} bg={C.goldLight} title="Recording a verdict needs a signed-in account">
            read-only · sign in on #/admin
          </Chip>
        ) : null}
      </header>

      <main style={{ maxWidth: 980, margin: "0 auto", padding: 20, display: "grid", gap: 16 }}>
        <Card style={{ display: "grid", gap: 10 }}>
          <h1 style={{ margin: 0, fontFamily: "Fraunces, serif", fontSize: 21, fontWeight: 600, color: C.navy }}>
            Is the nutrition plausible?
          </h1>
          <p style={{ margin: 0, fontSize: 12.5, color: C.subtext, lineHeight: 1.7 }}>
            Energy is the only nutrient Food.com publishes <em>and</em> we can compute, so the ratio
            below is the one measurement of the gram chain we have. Iron, calcium, zinc, folate and
            vitamin C exist only by computation — they carry the same error, and nothing catches it.
            Ordered worst first.
          </p>
          {payload ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {[
                { id: "all", label: `All ${payload.count}` },
                { id: "worst", label: "Off by more than half" },
                { id: "unreviewed", label: `Unreviewed ${payload.unreviewed}` },
                { id: "reviewed", label: `Reviewed ${payload.reviewed}` },
              ].map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setFilter(option.id)}
                  style={{
                    padding: "5px 11px",
                    borderRadius: 999,
                    border: `1px solid ${filter === option.id ? C.accent : C.border}`,
                    background: filter === option.id ? C.accentLight : C.white,
                    color: filter === option.id ? C.accent : C.subtext,
                    fontSize: 11.5,
                    fontWeight: 600,
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
        </Card>

        {error ? (
          <Card>
            <span style={{ fontSize: 12.5, color: C.coral }}>Could not load the queue: {error}</span>
          </Card>
        ) : null}

        {!payload && !error ? (
          <Card>
            <span style={{ fontSize: 12.5, color: C.muted }}>Loading the fifty recipes…</span>
          </Card>
        ) : null}

        {items.map((item) => (
          <Row key={item.recipe_id} item={item} busy={busy} onVerdict={onVerdict} />
        ))}
      </main>
    </div>
  );
}
