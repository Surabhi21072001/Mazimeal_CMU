// Who is looking at the screen.
//
// This is the review screen's own local reviewer, and it is deliberately still
// here. Real sign-in now exists - shared/services/auth/authStore.js, used by
// #/admin and by the nutrition review - but it is asynchronous, and every
// caller of getSession() below reads it synchronously during render. Swapping
// it would mean reworking those screens, which is a separate change.
//
// What matters is that nothing with consequences depends on this file any
// more: the API decides who may write, from the verified token, and both
// tables behind those writes are closed to the browser's keys entirely.
//
// Nothing security-relevant hangs on this. The admin screens are hidden from
// people who are not reviewers, but hiding a screen is a convenience, not a
// control - the database decides who may actually write, through its own
// policies. The anon key ships inside the browser bundle, so anyone can call
// the API directly whatever this function says.
const OVERRIDE_KEY = "mazimeal:session-override";

const DEFAULT_SESSION = {
  user_id: "local-reviewer",
  name: "Kevin",
  role: "admin", // until login exists, the person running this is the reviewer
};

export function getSession() {
  try {
    const raw = window.localStorage.getItem(OVERRIDE_KEY);
    if (raw) return { ...DEFAULT_SESSION, ...JSON.parse(raw) };
  } catch {
    // private window, or someone put junk in storage; the default is fine
  }
  return DEFAULT_SESSION;
}

export function isAdmin() {
  return getSession().role === "admin";
}

// Lets us see the screens as a normal user without building login first:
//   localStorage.setItem("mazimeal:session-override", '{"role":"member"}')
export function setSessionOverride(partial) {
  try {
    window.localStorage.setItem(OVERRIDE_KEY, JSON.stringify(partial));
  } catch {
    // nothing to do; the default session still applies
  }
}
