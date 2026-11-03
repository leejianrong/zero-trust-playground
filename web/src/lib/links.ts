export type Link = { id: string; name: string; url: string; purpose: string; start: string; up: boolean };

/** What to tell the learner about a tool: how it is doing, and what to do about it. */
export function describe(link: Link) {
  return link.up
    ? { label: "Up", detail: "Ready to open." }
    : { label: "Down", detail: `Not answering. Start it with: ${link.start}` };
}
