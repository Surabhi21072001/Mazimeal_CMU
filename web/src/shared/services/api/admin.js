// The rule admin endpoints. Transport and identity live in authed.js.
import { ApiError, call } from "./authed";

export { ApiError };

// Who the server thinks is calling, and whether they may approve anything.
export function whoAmI() {
  return call("/api/admin/me");
}

// Reading rules needs no account: they are published research, and the cook
// screens already show them.
export function ruleSummary() {
  return call("/api/admin/rules/summary", { auth: false });
}

export function listRules({ q, category, status, reach, active, limit } = {}) {
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (category) query.set("category", category);
  if (status) query.set("status", status);
  if (reach) query.set("reach", reach);
  if (active != null) query.set("active", String(active));
  if (limit) query.set("limit", String(limit));
  const suffix = query.toString() ? `?${query}` : "";
  return call(`/api/admin/rules${suffix}`, { auth: false });
}

export function getRule(ruleId) {
  return call(`/api/admin/rules/${encodeURIComponent(ruleId)}`, { auth: false });
}

export function submitRuleRequest({ kind = "update", ruleId, proposed = {}, note }) {
  return call("/api/admin/rule-requests", {
    method: "POST",
    body: { kind, rule_id: ruleId, proposed, note },
  });
}

export function listRuleRequests(status = "pending") {
  return call(`/api/admin/rule-requests?status=${encodeURIComponent(status)}`);
}

export function decideRuleRequest(requestId, approve, note) {
  return call(`/api/admin/rule-requests/${encodeURIComponent(requestId)}/decide`, {
    method: "POST",
    body: { approve, note },
  });
}

// The reviewer list. Reading it needs to be a reviewer too: it is a list of
// named people, and nothing about the admin screen needs it to be public.
export function listPeople() {
  return call("/api/admin/people");
}

export function grantAdmin(email, note) {
  return call("/api/admin/people", { method: "POST", body: { email, note } });
}

export function revokeAdmin(email) {
  return call(`/api/admin/people/${encodeURIComponent(email)}`, { method: "DELETE" });
}
