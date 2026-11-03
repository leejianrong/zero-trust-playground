import { expect, it } from "vitest";
import { describe as describeLink, type Link } from "./links";

const link = (up: boolean): Link => ({ id: "x", name: "X", url: "http://x", purpose: "p", start: "make x", up });

it("says a running tool is ready", () => {
  expect(describeLink(link(true))).toEqual({ label: "Up", detail: "Ready to open." });
});
it("tells the learner how to start a tool that is not answering", () => {
  expect(describeLink(link(false))).toEqual({ label: "Down", detail: "Not answering. Start it with: make x" });
});
