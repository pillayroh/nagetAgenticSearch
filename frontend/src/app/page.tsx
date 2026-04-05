"use client";

import { useCallback, useMemo, useState } from "react";

type Source = { url: string; evidence: string };
type Cell = {
  value: string | null;
  confidence?: number;
  sources?: Source[];
};

type EntityRow = { cells: Record<string, Cell> };

type SearchResponse = {
  run_id: string;
  query: string;
  column_order: string[];
  entities: EntityRow[];
  search_urls: string[];
  meta: Record<string, unknown>;
};

const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

const G_COLORS = ["#4285F4", "#EA4335", "#FBBC05", "#34A853"] as const;

function ColorWord({
  text,
  className = "",
}: {
  text: string;
  className?: string;
}) {
  return (
    <span className={className}>
      {text.split("").map((c, i) => (
        <span key={`${c}-${i}`} style={{ color: G_COLORS[i % G_COLORS.length] }}>
          {c}
        </span>
      ))}
    </span>
  );
}

function slugKey(s: string): string {
  return s.toLowerCase().replace(/[\s-]+/g, "_");
}

function parseSources(o: Record<string, unknown>): Source[] {
  return Array.isArray(o.sources) ? (o.sources as Source[]) : [];
}

function asCell(raw: unknown): Cell | null {
  if (raw == null) return null;
  if (typeof raw === "string" || typeof raw === "number")
    return { value: String(raw), sources: [] };
  if (typeof raw === "object" && raw !== null) {
    const o = raw as Record<string, unknown>;
    if ("value" in o) {
      let v: unknown = o.value;
      if (typeof v === "object" && v !== null) {
        const inner = v as Record<string, unknown>;
        if (typeof inner.text === "string") v = inner.text;
        else if (typeof inner.content === "string") v = inner.content;
      }
      return {
        value:
          v == null
            ? null
            : typeof v === "string"
              ? v
              : String(v),
        confidence: typeof o.confidence === "number" ? o.confidence : undefined,
        sources: parseSources(o),
      };
    }
    const alts = [
      "text",
      "content",
      "description",
      "name",
      "title",
      "summary",
      "label",
    ];
    for (const k of alts) {
      const x = o[k];
      if (typeof x === "string" && x.trim()) {
        return {
          value: x,
          confidence: typeof o.confidence === "number" ? o.confidence : undefined,
          sources: parseSources(o),
        };
      }
    }
    for (const [k, x] of Object.entries(o)) {
      if (k === "sources" || k === "confidence") continue;
      if (typeof x === "string" && x.trim()) {
        return {
          value: x,
          confidence: typeof o.confidence === "number" ? o.confidence : undefined,
          sources: parseSources(o),
        };
      }
    }
  }
  return null;
}

function resolveCellRaw(row: Record<string, unknown>, col: string): unknown {
  const cells = row.cells as Record<string, unknown> | undefined;
  if (cells && col in cells) return cells[col];
  if (cells && typeof cells === "object") {
    const want = slugKey(col);
    for (const k of Object.keys(cells)) {
      if (slugKey(k) === want) return cells[k];
    }
  }
  if (col in row && col !== "cells") return row[col];
  return undefined;
}

/** SERP/Yelp-style evidence → readable paragraph (strip "1. … · 2. …" list markers). */
function evidenceToParagraph(raw: string): string {
  let t = (raw ?? "").trim().replace(/\s+/g, " ");
  if (!t) return "";
  t = t.replace(/\u00b7/g, "·").replace(/\s*·\s*/g, " · ");
  const stripNum = (seg: string) => seg.replace(/^\d+\.\s*/, "").trim();
  if (t.includes(" · ")) {
    const segments = t
      .split(/\s*·\s*/)
      .map(stripNum)
      .filter(Boolean)
      .map((s) => (s.endsWith(".") ? s : `${s}.`));
    return segments.join(" ");
  }
  const byNumber = t
    .split(/\s+(?=\d+\.\s)/)
    .map(stripNum)
    .filter(Boolean)
    .map((s) => (s.endsWith(".") ? s : `${s}.`));
  if (byNumber.length > 1) {
    return byNumber.join(" ");
  }
  return t;
}

function HeroSearchBar({
  query,
  onChange,
  onSubmit,
  loading,
}: {
  query: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <div className="mx-auto flex w-full max-w-[584px] flex-col items-stretch">
      <div className="flex h-11 items-center rounded-full border border-[#5f6368] bg-[#303134] px-4 shadow-sm transition-all hover:border-[#8ab4f8]/35 focus-within:border-[#8ab4f8]/70 focus-within:shadow-[0_0_0_1px_rgba(138,180,248,0.35)] md:h-[44px]">
        <svg
          className="mr-3 h-5 w-5 shrink-0 text-[#9aa0a6]"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden
        >
          <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
        </svg>
        <input
          className="min-w-0 flex-1 border-0 bg-transparent text-base text-[#e8eaed] outline-none placeholder:text-[#9aa0a6]"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !loading && query.trim()) onSubmit();
          }}
          aria-label="Search"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
        />
      </div>
      <div className="mt-8 flex justify-center gap-3">
        <button
          type="button"
          onClick={onSubmit}
          disabled={loading || !query.trim()}
          className="rounded-lg border border-[#5f6368] bg-[#303134] px-5 py-2.5 text-sm font-medium text-[#e8eaed] transition-colors hover:bg-[#3c4043] hover:border-[#70757a] disabled:cursor-not-allowed disabled:opacity-45"
        >
          {loading ? "Searching" : "Search"}
        </button>
      </div>
    </div>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [openCell, setOpenCell] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) return;
    setHasSearched(true);
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const r = await fetch(`${API}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      if (!r.ok) {
        const t = await r.text();
        throw new Error(t || r.statusText);
      }
      const json = (await r.json()) as SearchResponse;
      setData(json);
    } catch (e) {
      const raw = e instanceof Error ? e.message : "Request failed";
      const isNetwork =
        raw === "Failed to fetch" ||
        raw === "Load failed" ||
        raw.toLowerCase().includes("network");
      if (isNetwork) {
        setError(
          `Cannot reach the API (${API}). On Vercel set NEXT_PUBLIC_API_URL to your Render API (https, no trailing slash). If the API is up, wait ~60s for Render cold start and retry. Origin: ${typeof window !== "undefined" ? window.location.origin : ""}`,
        );
      } else {
        setError(raw);
      }
    } finally {
      setLoading(false);
    }
  }, [query]);

  const downloadJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `run-${data.run_id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const cols = useMemo(() => {
    if (!data?.entities?.length) return [];
    const first = data.entities[0] as Record<string, unknown>;
    const cellKeys =
      first.cells && typeof first.cells === "object"
        ? Object.keys(first.cells as object)
        : [];
    const co = data.column_order || [];
    if (!co.length) return cellKeys;
    const allMatch = co.every(
      (c) =>
        cellKeys.includes(c) ||
        cellKeys.some((k) => slugKey(k) === slugKey(c)),
    );
    if (allMatch) return co;
    return cellKeys.length ? cellKeys : co;
  }, [data]);

  const timings = data?.meta?.timings_s as
    | { search_scrape?: number; llm?: number }
    | undefined;
  const provider = data?.meta?.search_provider as string | undefined;
  const snippetPages = data?.meta?.pages_from_snippet as number | undefined;
  const httpPages = data?.meta?.pages_fetched_http as number | undefined;

  const showResultsLayout = hasSearched;

  return (
    <div className="min-h-screen bg-[#202124]">
      {!showResultsLayout ? (
        <main className="google-dark-hero-glow flex flex-col items-center px-4 pb-16 pt-[10vh] sm:pt-[15vh]">
          <h1 className="mb-10 text-center text-[40px] font-normal leading-none tracking-tight sm:text-[56px]">
            <ColorWord text="Agentic" />
            <span className="text-[#bdc1c6]"> Search</span>
          </h1>
          <div className="flex w-full max-w-[584px] flex-col items-center">
            <HeroSearchBar
              query={query}
              onChange={setQuery}
              onSubmit={runSearch}
              loading={loading}
            />
            {loading && (
              <div
                className="mt-10 flex items-center gap-1"
                role="status"
                aria-live="polite"
              >
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#4285F4]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#EA4335]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#FBBC05]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#34A853]" />
              </div>
            )}
            {error && (
              <p className="mt-8 max-w-lg text-center text-sm text-[#f28b82]">
                {error}
              </p>
            )}
          </div>
        </main>
      ) : (
        <>
          <header className="sticky top-0 z-20 border-b border-[#3c4043] bg-[#202124]/90 px-4 py-3 backdrop-blur-md md:px-8">
            <div className="mx-auto flex max-w-[1200px] items-center gap-4 md:gap-8">
              <button
                type="button"
                onClick={() => {
                  setHasSearched(false);
                  setData(null);
                  setError(null);
                }}
                className="shrink-0 text-left text-base font-normal leading-none md:text-lg"
                aria-label="New search"
              >
                <ColorWord text="Agentic" />
                <span className="text-[#bdc1c6]"> Search</span>
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <div
                    className="flex h-10 min-w-0 flex-1 items-center rounded-full border border-[#5f6368] bg-[#303134] px-3 shadow-sm transition-all hover:border-[#8ab4f8]/35 focus-within:border-[#8ab4f8]/70 focus-within:shadow-[0_0_0_1px_rgba(138,180,248,0.35)]"
                  >
                    <svg
                      className="mr-2 h-4 w-4 shrink-0 text-[#9aa0a6]"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      aria-hidden
                    >
                      <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
                    </svg>
                    <input
                      className="min-w-0 flex-1 border-0 bg-transparent text-sm text-[#e8eaed] outline-none"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !loading && query.trim())
                          runSearch();
                      }}
                      aria-label="Search"
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={runSearch}
                    disabled={loading || !query.trim()}
                    className="shrink-0 rounded-lg border border-[#5f6368] bg-[#303134] px-3 py-2 text-sm font-medium text-[#e8eaed] hover:bg-[#3c4043] disabled:opacity-45"
                  >
                    {loading ? "…" : "Search"}
                  </button>
                </div>
              </div>
            </div>
          </header>

          <div className="mx-auto max-w-[1200px] px-4 py-4 text-[#e8eaed] md:px-8">
            {loading && (
              <div className="flex items-center gap-1 py-6" role="status">
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#4285F4]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#EA4335]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#FBBC05]" />
                <span className="google-loading-dot h-2 w-2 rounded-full bg-[#34A853]" />
              </div>
            )}

            {error && (
              <p className="py-4 text-sm text-[#f28b82] whitespace-pre-wrap">
                {error}
              </p>
            )}

            {data && (
              <section className="space-y-5 pb-16 pt-2">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <p className="text-sm text-[#9aa0a6]">
                      About {data.entities.length} result
                      {data.entities.length !== 1 ? "s" : ""} ·{" "}
                      <span className="font-mono text-xs text-[#9aa0a6]">
                        {data.run_id}
                      </span>
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#9aa0a6]">
                      {timings && (
                        <span>
                          {timings.search_scrape}s · {timings.llm}s
                        </span>
                      )}
                      {provider && <span>· {provider}</span>}
                      {snippetPages != null && snippetPages > 0 && (
                        <span>· {snippetPages} snippet</span>
                      )}
                      {httpPages != null && httpPages > 0 && (
                        <span>· {httpPages} fetched</span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={downloadJson}
                    className="text-left text-sm text-[#8ab4f8] hover:text-[#aecbfa] hover:underline"
                  >
                    Download JSON
                  </button>
                </div>

                <div className="overflow-x-auto rounded-2xl border border-[#3c4043] bg-[#303134]/40 shadow-sm">
                  <table className="min-w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-[#3c4043] bg-[#303134]">
                        <th className="w-10 px-3 py-2 text-xs font-medium text-[#9aa0a6]">
                          #
                        </th>
                        {cols.map((c) => (
                          <th
                            key={c}
                            className="px-3 py-2 text-xs font-medium capitalize text-[#e8eaed]"
                          >
                            {c.replace(/_/g, " ")}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.entities.map((row, i) => (
                        <tr
                          key={i}
                          className="border-b border-[#3c4043] last:border-0 hover:bg-[#3c4043]/40"
                        >
                          <td className="px-3 py-3 align-top font-mono text-xs text-[#9aa0a6]">
                            {i + 1}
                          </td>
                          {cols.map((col) => {
                            const raw = resolveCellRaw(
                              row as Record<string, unknown>,
                              col,
                            );
                            const cell = asCell(raw);
                            const key = `${i}-${col}`;
                            const open = openCell === key;
                            const srcCount = cell?.sources?.length ?? 0;
                            const display =
                              cell?.value != null &&
                              String(cell.value).trim() !== ""
                                ? String(cell.value)
                                : "";
                            return (
                              <td
                                key={col}
                                className="max-w-[22rem] px-3 py-3 align-top text-[#e8eaed]"
                              >
                                <div className="leading-relaxed">{display}</div>
                                {cell?.confidence != null && (
                                  <span className="mt-1 inline-block text-xs text-[#9aa0a6]">
                                    {Math.round((cell.confidence || 0) * 100)}%
                                  </span>
                                )}
                                {srcCount > 0 && (
                                  <button
                                    type="button"
                                    className="mt-1 block text-left text-xs text-[#8ab4f8] hover:text-[#aecbfa] hover:underline"
                                    onClick={() =>
                                      setOpenCell(open ? null : key)
                                    }
                                  >
                                    {open
                                      ? "Hide sources"
                                      : `${srcCount} source${srcCount > 1 ? "s" : ""}`}
                                  </button>
                                )}
                                {open && cell?.sources && (
                                  <ul className="mt-2 space-y-2 border-l-2 border-[#5f6368] pl-3 text-xs text-[#bdc1c6]">
                                    {cell.sources.map((s, j) => (
                                      <li key={j} className="space-y-2">
                                        <p className="m-0 text-[13px] leading-relaxed text-[#e8eaed] text-pretty">
                                          {evidenceToParagraph(
                                            typeof s.evidence === "string"
                                              ? s.evidence
                                              : String(s.evidence ?? ""),
                                          )}
                                        </p>
                                        <a
                                          href={s.url}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="inline-block max-w-full break-all font-mono text-[11px] text-[#8ab4f8] hover:text-[#aecbfa] hover:underline"
                                        >
                                          {s.url}
                                        </a>
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <details className="rounded-2xl border border-[#3c4043] bg-[#303134]/40 px-4 py-3 text-sm">
                  <summary className="cursor-pointer text-[#e8eaed]">
                    Source URLs ({data.search_urls.length})
                  </summary>
                  <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto">
                    {data.search_urls.map((u) => (
                      <li key={u}>
                        <a
                          href={u}
                          className="break-all font-mono text-xs text-[#8ab4f8] hover:text-[#aecbfa] hover:underline"
                          target="_blank"
                          rel="noreferrer"
                        >
                          {u}
                        </a>
                      </li>
                    ))}
                  </ul>
                </details>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  );
}
