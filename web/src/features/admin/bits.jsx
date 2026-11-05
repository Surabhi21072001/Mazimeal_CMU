// Presentational pieces for the admin screens. Components only, so the file
// satisfies react-refresh/only-export-components; the formatting helpers live
// in format.js beside it.
import { C } from "../../shared/theme/colors";

export function Card({ children, style, ...rest }) {
  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 14,
        padding: 18,
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Chip({ children, color = C.subtext, bg = "transparent", border, title }) {
  return (
    <span
      title={title}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 10.5,
        fontWeight: 700,
        letterSpacing: 0.2,
        color,
        background: bg,
        border: border ? `1px solid ${border}` : "1px solid transparent",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

// A number with what it counts under it. The hint is for the counts that are
// easy to misread - "13 reachable" means nothing without "of 54 active".
export function Tile({ label, value, hint, tone = C.navy }) {
  return (
    <Card style={{ padding: "14px 16px", display: "grid", gap: 2 }}>
      <span style={{ fontSize: 24, fontWeight: 700, color: tone, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </span>
      <span style={{ fontSize: 11.5, fontWeight: 600, color: C.subtext }}>{label}</span>
      {hint ? <span style={{ fontSize: 10.5, color: C.muted, lineHeight: 1.5 }}>{hint}</span> : null}
    </Card>
  );
}

export function Button({ children, onClick, disabled, tone = "normal", type = "button", style }) {
  const palette = {
    normal: { bg: C.white, fg: C.navy, border: C.border },
    primary: { bg: C.accent, fg: C.white, border: C.accent },
    danger: { bg: C.white, fg: C.coral, border: C.coral },
  }[tone];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "7px 13px",
        borderRadius: 9,
        border: `1px solid ${disabled ? C.border : palette.border}`,
        background: disabled ? C.bg : palette.bg,
        color: disabled ? C.dim : palette.fg,
        fontSize: 12.5,
        fontWeight: 600,
        cursor: disabled ? "default" : "pointer",
        fontFamily: "inherit",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label style={{ display: "grid", gap: 4 }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: C.subtext, letterSpacing: 0.3 }}>
        {label}
      </span>
      {children}
      {hint ? <span style={{ fontSize: 10.5, color: C.muted }}>{hint}</span> : null}
    </label>
  );
}

export function TextInput({ value, onChange, placeholder, multiline, rows = 3, ...rest }) {
  const shared = {
    width: "100%",
    boxSizing: "border-box",
    padding: "8px 10px",
    borderRadius: 9,
    border: `1px solid ${C.border}`,
    background: C.white,
    color: C.text,
    fontSize: 13,
    fontFamily: "inherit",
    lineHeight: 1.5,
  };
  if (multiline) {
    return (
      <textarea
        value={value ?? ""}
        rows={rows}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        style={{ ...shared, resize: "vertical" }}
        {...rest}
      />
    );
  }
  return (
    <input
      value={value ?? ""}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      style={shared}
      {...rest}
    />
  );
}

export function Select({ value, onChange, options, placeholder = "Any" }) {
  return (
    <select
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value || null)}
      style={{
        padding: "8px 10px",
        borderRadius: 9,
        border: `1px solid ${C.border}`,
        background: C.white,
        color: C.text,
        fontSize: 13,
        fontFamily: "inherit",
      }}
    >
      <option value="">{placeholder}</option>
      {options.map((option) => {
        const { value: v, label } = typeof option === "string" ? { value: option, label: option } : option;
        return (
          <option key={v} value={v}>
            {label}
          </option>
        );
      })}
    </select>
  );
}

export function Notice({ kind = "info", children }) {
  const tone = { info: C.subtext, error: C.coral, ok: C.accent }[kind];
  const bg = { info: C.bg, error: C.coralLight, ok: C.accentLight }[kind];
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      style={{
        padding: "10px 12px",
        borderRadius: 10,
        background: bg,
        color: tone,
        fontSize: 12.5,
        lineHeight: 1.6,
      }}
    >
      {children}
    </div>
  );
}
