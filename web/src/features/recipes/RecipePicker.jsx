// Picking one recipe out of fifty.
//
// A tab strip worked for three recipes and stops working at fifty - the names
// are long, the strip scrolls sideways, and finding "Gallo Pinto" means
// dragging past forty others. So: a combobox. Type a word from the name or the
// cuisine and the list narrows; arrows and Enter work, because the people
// testing this drive it from the keyboard.
//
// It filters on words, not on the whole string, so "bean rice" finds "Gallo
// Pinto (Costa Rican Rice and Beans)" and the order typed does not matter.
import { useEffect, useMemo, useRef, useState } from "react";
import { C } from "../../shared/theme/colors";
import { matches } from "./search";

export default function RecipePicker({ items, currentId, onPick, onBrowseAll }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const wrap = useRef(null);
  const input = useRef(null);
  const listbox = useRef(null);

  const selectable = useMemo(() => items.filter((item) => item.recipe_id), [items]);
  const shown = useMemo(() => selectable.filter((item) => matches(item, query)), [selectable, query]);
  const current = selectable.find((item) => item.recipe_id === currentId);

  useEffect(() => {
    if (!open) return undefined;
    // Closing on an outside click rather than on blur: blur fires when the
    // pointer goes down on the list itself, which would close it before the
    // click lands.
    const away = (event) => {
      if (wrap.current && !wrap.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    input.current?.focus();
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  useEffect(() => {
    // Keep the highlighted row in view while arrowing through a long list.
    listbox.current?.querySelector('[data-cursor="true"]')?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  const choose = (item) => {
    setOpen(false);
    setQuery("");
    if (item?.recipe_id && item.recipe_id !== currentId) onPick(item.recipe_id);
  };

  const onKeyDown = (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!shown.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setCursor((value) => (value + step + shown.length) % shown.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(shown[cursor]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    }
  };

  return (
    <div ref={wrap} style={{ position: "relative", flex: "1 1 240px", maxWidth: 420, minWidth: 0 }}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Pick another recipe"
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          borderRadius: 10,
          border: `1px solid ${open ? C.accent : C.border}`,
          background: C.white,
          color: C.text,
          fontSize: 12.5,
          fontWeight: 600,
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span
          style={{
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {current?.name || "Choose a recipe"}
        </span>
        {selectable.length ? (
          <span style={{ fontSize: 10.5, color: C.muted, fontWeight: 600 }}>{selectable.length}</span>
        ) : null}
        <span style={{ color: C.muted, fontSize: 10 }}>{open ? "▲" : "▼"}</span>
      </button>

      {open ? (
        <div
          style={{
            position: "absolute",
            zIndex: 30,
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: C.surface,
            border: `1px solid ${C.border}`,
            borderRadius: 12,
            boxShadow: "0 12px 28px rgba(22,49,39,0.16)",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: 8, borderBottom: `1px solid ${C.border}` }}>
            <input
              ref={input}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setCursor(0);
              }}
              onKeyDown={onKeyDown}
              placeholder="Search by name or cuisine…"
              aria-label="Search recipes"
              style={{
                width: "100%",
                boxSizing: "border-box",
                padding: "7px 10px",
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                background: C.white,
                color: C.text,
                fontSize: 12.5,
                outline: "none",
              }}
            />
          </div>

          <div ref={listbox} role="listbox" style={{ maxHeight: 320, overflowY: "auto" }}>
            {shown.map((item, index) => {
              const active = index === cursor;
              const isCurrent = item.recipe_id === currentId;
              return (
                <button
                  key={item.recipe_id}
                  type="button"
                  role="option"
                  aria-selected={isCurrent}
                  data-cursor={active ? "true" : undefined}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => choose(item)}
                  style={{
                    width: "100%",
                    display: "grid",
                    gap: 2,
                    padding: "8px 12px",
                    border: "none",
                    borderLeft: `3px solid ${isCurrent ? C.accent : "transparent"}`,
                    background: active ? C.accentLight : "transparent",
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <span
                    style={{
                      fontSize: 12.5,
                      fontWeight: isCurrent ? 700 : 600,
                      color: isCurrent ? C.accentDark : C.text,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {item.name}
                  </span>
                  <span style={{ fontSize: 10.5, color: C.muted }}>
                    {[
                      item.cuisine,
                      item.rule_count > 0
                        ? `${item.rule_count} ${item.rule_count === 1 ? "rule" : "rules"}`
                        : "no rules",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </button>
              );
            })}

            {shown.length === 0 ? (
              <p style={{ margin: 0, padding: "14px 12px", fontSize: 12, color: C.muted }}>
                Nothing matches “{query}”.
              </p>
            ) : null}
          </div>

          {onBrowseAll ? (
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onBrowseAll();
              }}
              style={{
                width: "100%",
                padding: "9px 12px",
                border: "none",
                borderTop: `1px solid ${C.border}`,
                background: C.card,
                color: C.subtext,
                fontSize: 11.5,
                fontWeight: 600,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              Browse all {selectable.length} with filters &rarr;
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
