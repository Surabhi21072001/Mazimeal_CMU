// The signed-in person's own profile.
//
// Nothing about who is asking is in the request: the account comes out of the
// verified token on the server (see api/app/profile.py). The older path the
// rules engine offers - ?user_id=<uuid> - makes the identifier the credential,
// so the app does not use it.
import { call } from "./authed";

export async function getMyProfile() {
  return call("/api/profile/me");
}
