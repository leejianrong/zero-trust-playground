export type Ev = {
  id: number;
  ts: number;
  kind: string;
  src: string | null;
  evidence: Record<string, string>;
};

export type Svid = { serial: string; notBefore: number; notAfter: number };

export type Card = {
  spiffeId: string;
  workload: string;
  history: Svid[]; // newest first; history[0] is the current SVID
  registrationRemoved: boolean;
};

export type Cards = Record<string, Card>;

export function reduce(cards: Cards, ev: Ev): Cards {
  if (!ev.src) return cards;
  const card = cards[ev.src];
  if (ev.kind === "svid_issued") {
    const svid: Svid = {
      serial: ev.evidence.serial,
      notBefore: Date.parse(ev.evidence.not_before),
      notAfter: Date.parse(ev.evidence.not_after),
    };
    if (card?.history[0].serial === svid.serial) return cards;
    return {
      ...cards,
      [ev.src]: {
        spiffeId: ev.src,
        workload: ev.evidence.workload,
        history: [svid, ...(card?.history ?? [])].slice(0, 8),
        registrationRemoved: false,
      },
    };
  }
  if (card && (ev.kind === "entry_removed" || ev.kind === "entry_added")) {
    return { ...cards, [ev.src]: { ...card, registrationRemoved: ev.kind === "entry_removed" } };
  }
  return cards;
}

export function parseSpiffeId(id: string) {
  const m = /^spiffe:\/\/([^/]+)\/ns\/([^/]+)\/sa\/([^/]+)$/.exec(id);
  return m ? { trustDomain: m[1], namespace: m[2], serviceAccount: m[3] } : null;
}

/** Fraction of the SVID's validity window still left, clamped to 0..1. */
export function lifeLeft(svid: Svid, now: number): number {
  const span = svid.notAfter - svid.notBefore;
  return span <= 0 ? 0 : Math.min(1, Math.max(0, (svid.notAfter - now) / span));
}

export function secondsLeft(svid: Svid, now: number): number {
  return Math.max(0, Math.ceil((svid.notAfter - now) / 1000));
}

export const isExpired = (svid: Svid, now: number) => now >= svid.notAfter;
