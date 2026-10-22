import { useEffect, useState } from "react";

export type Route =
  | { page: "home" }
  | { page: "org"; org: string }
  | { page: "project"; org: string; project: string }
  | { page: "pack"; org: string; project: string | null; pack: string } // pack "new" = create
  | { page: "analysis"; org: string; project: string; id: string; finding?: string }
  | { page: "document"; org: string; project: string; id: string; path: string; finding?: string };

const HEX = "([a-f0-9]{12})";
const PATTERNS: [RegExp, (m: RegExpMatchArray, finding?: string) => Route][] = [
  [new RegExp(`^/o/${HEX}/p/${HEX}/a/${HEX}/doc/(.+)$`), (m, finding) => ({ page: "document", org: m[1], project: m[2], id: m[3], path: decodeURIComponent(m[4]), finding })],
  [new RegExp(`^/o/${HEX}/p/${HEX}/a/${HEX}/?$`), (m, finding) => ({ page: "analysis", org: m[1], project: m[2], id: m[3], finding })],
  [new RegExp(`^/o/${HEX}/p/${HEX}/packs/([a-z0-9-]+)$`), (m) => ({ page: "pack", org: m[1], project: m[2], pack: m[3] })],
  [new RegExp(`^/o/${HEX}/p/${HEX}/?$`), (m) => ({ page: "project", org: m[1], project: m[2] })],
  [new RegExp(`^/o/${HEX}/packs/([a-z0-9-]+)$`), (m) => ({ page: "pack", org: m[1], project: null, pack: m[2] })],
  [new RegExp(`^/o/${HEX}/?$`), (m) => ({ page: "org", org: m[1] })],
];

/** #/o/<org>/p/<project>/a/<analysis>/doc/<path>?f=<finding> and the shorter prefixes. No router dependency. */
export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const finding = new URLSearchParams(query).get("f") ?? undefined;
  for (const [pattern, build] of PATTERNS) {
    const m = path.match(pattern);
    if (m) return build(m, finding);
  }
  return { page: "home" };
}

export function href(route: Route): string {
  const f = "finding" in route && route.finding ? `?f=${encodeURIComponent(route.finding)}` : "";
  switch (route.page) {
    case "home": return "#/";
    case "org": return `#/o/${route.org}`;
    case "project": return `#/o/${route.org}/p/${route.project}`;
    case "pack": return route.project ? `#/o/${route.org}/p/${route.project}/packs/${route.pack}` : `#/o/${route.org}/packs/${route.pack}`;
    case "analysis": return `#/o/${route.org}/p/${route.project}/a/${route.id}${f}`;
    case "document": return `#/o/${route.org}/p/${route.project}/a/${route.id}/doc/${encodeURIComponent(route.path)}${f}`;
  }
}

export function navigate(route: Route, replace = false) {
  if (replace) {
    history.replaceState(null, "", href(route));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    location.hash = href(route);
  }
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
