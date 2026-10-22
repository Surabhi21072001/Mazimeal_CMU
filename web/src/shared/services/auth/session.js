// Who is looking at the screen.
//
// Login is not built yet, so this returns a fixed reviewer. When Supabase Auth
// is wired in, only this file changes: read the session, look up the user's
// role, and return it here.
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
