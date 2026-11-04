import { expect, test } from "vitest";
import { reduce, type UserEv, type Users } from "./users";

const empty: Users = { people: {}, requests: [], failures: [] };
let id = 0;
const ev = (kind: string, src: string | null, extra: Partial<UserEv> = {}): UserEv =>
  ({ id: ++id, ts: 1000 + id, layer: "user", kind, verdict: "info", src, dst: "web", reason: "r", evidence: {}, ...extra }) as UserEv;

test("a sign-in puts the person on the list as signed in", () => {
  const s = reduce(empty, ev("user_login", "aisha", { verdict: "allow", dst: "web" }));
  expect(s.people.aisha).toMatchObject({ user: "aisha", signedIn: true, logins: 1, client: "web" });
});

test("a sign-out marks them signed out, and a later sign-in marks them in again", () => {
  let s = reduce(empty, ev("user_login", "bob"));
  s = reduce(s, ev("user_logout", "bob"));
  expect(s.people.bob.signedIn).toBe(false);
  s = reduce(s, ev("user_login", "bob"));
  expect(s.people.bob).toMatchObject({ signedIn: true, logins: 2 });
});

test("a request shows who it was for, which client sent it and which audience the token named", () => {
  const s = reduce(empty, ev("user_authorisation", "bob", {
    verdict: "deny", dst: "records-api", reason: "bob has receptionist, which does not allow write",
    evidence: { subject: "0e5a", roles: ["receptionist"], client: "web", audience: ["records-api"], method: "POST", route: "/patients", decision: "deny" },
  }));
  expect(s.requests[0]).toMatchObject({ user: "bob", client: "web", audience: ["records-api"], method: "POST", route: "/patients", verdict: "deny" });
  expect(s.people.bob).toMatchObject({ roles: ["receptionist"], refused: 1 });
});

test("a request with no token is listed under anonymous and is not a person", () => {
  const s = reduce(empty, ev("user_authorisation", "anonymous", { verdict: "deny", dst: "records-api", evidence: { roles: [], audience: [], client: null } }));
  expect(s.requests[0].user).toBe("anonymous");
  expect(s.people.anonymous).toBeUndefined();
});

test("a failed sign-in is listed as a failure and does not make a person", () => {
  const s = reduce(empty, ev("user_login_failed", "bob", { verdict: "deny", reason: "bob could not sign in to web: invalid_user_credentials" }));
  expect(s.failures[0].reason).toContain("invalid_user_credentials");
  expect(s.people.bob).toBeUndefined();
});

test("the lists keep only the newest rows, and unrelated events change nothing", () => {
  let s = empty;
  for (let i = 0; i < 20; i++) s = reduce(s, ev("user_authorisation", "aisha", { verdict: "allow", dst: "records-api", evidence: { roles: ["clinician"], audience: [] } }));
  expect(s.requests).toHaveLength(12);
  expect(reduce(s, ev("credential_issued", "records-api"))).toBe(s);
});
