import { useState } from "react";
import type { Works } from "../types";
import type { Action } from "../logic/state";

export function WorkList({ works, top, all, dispatch }: {
  works: Works | null; top: number[]; all?: number[]; dispatch: (a: Action) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!works) return <p className="muted small">Loading work titles…</p>;
  const shown = expanded && all ? [...top, ...all.filter((i) => !top.includes(i))] : top;
  return (
    <>
      <ol className="works">
        {shown.map((i) => (
          <li key={i}>
            <a href="#" onClick={(e) => { e.preventDefault(); dispatch({ type: "select", selection: { kind: "work", idx: i } }); }}>
              {works.title[i] ?? works.id[i]}
            </a>
            <div className="muted small">
              {works.year[i]} · {works.cited_by_count[i]} citations ·{" "}
              <a href={`https://openalex.org/${works.id[i]}`} target="_blank" rel="noreferrer">OpenAlex</a>
              {works.doi[i] && <> · <a href={`https://doi.org/${works.doi[i]}`} target="_blank" rel="noreferrer">DOI</a></>}
            </div>
          </li>
        ))}
      </ol>
      {all && all.length > top.length && (
        <button onClick={() => setExpanded(!expanded)}>{expanded ? "Show top 10" : `Show all ${all.length}`}</button>
      )}
    </>
  );
}
