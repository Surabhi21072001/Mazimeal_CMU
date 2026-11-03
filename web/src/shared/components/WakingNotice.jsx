// Waiting for the backend, with the reason on screen.
//
// The API runs on Render's free plan, which shuts the container down after 15
// minutes with no traffic. The next request then has to boot it, and Render
// says that takes up to a minute. A bare "Loading…" through that minute reads
// as a broken page - which is the worst thing it could do during a demo - so
// after a few seconds this says what is actually happening.
//
// The elapsed count is the honest progress indicator. A progress bar would
// have to invent a duration, since nothing tells the browser how far along a
// cold start is.
import { useEffect, useState } from "react";
import { C } from "../theme/colors";

const EXPLAIN_AFTER = 4; // seconds: long enough that a warm load never sees it
const SLOW_AFTER = 50; // seconds: past what Render quotes, so something is wrong

export default function WakingNotice({ what = "the recipe" }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const explaining = seconds >= EXPLAIN_AFTER;
  const slow = seconds >= SLOW_AFTER;

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        padding: "48px 20px",
        display: "grid",
        gap: 12,
        justifyItems: "center",
        textAlign: "center",
      }}
    >
      <style>{`
        @keyframes waking-pulse { 0%, 100% { opacity: 0.35 } 50% { opacity: 1 } }
        .waking-dot { animation: waking-pulse 1.4s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) { .waking-dot { animation: none; opacity: 0.7 } }
      `}</style>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          className="waking-dot"
          aria-hidden="true"
          style={{ width: 7, height: 7, borderRadius: "50%", background: C.accent }}
        />
        <span style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
          {explaining ? "Waking the server" : `Loading ${what}…`}
        </span>
      </div>

      {explaining ? (
        <p style={{ margin: 0, maxWidth: 420, fontSize: 12.5, color: C.subtext, lineHeight: 1.6 }}>
          The backend is on a free hosting plan that sleeps after 15 minutes without traffic, so the
          first request has to start it again. This takes up to a minute, once.
        </p>
      ) : null}

      {explaining ? (
        <span
          style={{
            fontSize: 11,
            color: C.muted,
            fontVariantNumeric: "tabular-nums",
            letterSpacing: 0.3,
          }}
        >
          {seconds}s
        </span>
      ) : null}

      {slow ? (
        <p style={{ margin: 0, maxWidth: 420, fontSize: 12, color: C.coral, lineHeight: 1.6 }}>
          Longer than a cold start usually takes. If the request fails, the screen falls back to the
          bundled sample data and says so in the top right.
        </p>
      ) : null}
    </div>
  );
}
