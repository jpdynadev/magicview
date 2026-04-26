"use client";

import type { HandSnapshot } from "@/lib/types";

interface ResultCardProps {
  snapshot: HandSnapshot;
  commander: string;
  deckName: string;
}

export function ResultCard({ snapshot, commander, deckName }: ResultCardProps) {
  const decisionClass =
    snapshot.decision === "KEEP" ? "decision-pill keep" : "decision-pill mulligan";

  return (
    <div className="panel stack gap-lg">
      <div className="result-header">
        <div className="stack gap-xs">
          <span className="eyebrow">{deckName}</span>
          <h2>{commander}</h2>
          <p>
            Mulligan #{snapshot.mulligan_number} from the {snapshot.seat_position} seat.
          </p>
        </div>
        <div className={decisionClass}>
          <strong>{snapshot.decision}</strong>
          <span>{Math.round(snapshot.confidence * 100)}% confidence</span>
        </div>
      </div>

      <div className="result-grid">
        <section className="subpanel stack gap-sm">
          <h3>Opening hand</h3>
          <div className="tag-grid">
            {snapshot.cards.map((card) => (
              <div key={card.name} className="mini-card">
                <strong>{card.name}</strong>
                <p>{card.summary}</p>
                <div className="mini-tags">
                  {card.tags.map((tag) => (
                    <span key={tag} className="mini-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="subpanel stack gap-sm">
          <h3>Reasoning</h3>
          <ul className="clean-list">
            {snapshot.reasoning.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </section>
      </div>

      <section className="subpanel stack gap-sm">
        <h3>Suggested first turns</h3>
        <div className="turn-grid">
          <div>
            <span className="turn-label">Turn 1</span>
            <p>{snapshot.turn_plan.turn_1}</p>
          </div>
          <div>
            <span className="turn-label">Turn 2</span>
            <p>{snapshot.turn_plan.turn_2}</p>
          </div>
          <div>
            <span className="turn-label">Turn 3</span>
            <p>{snapshot.turn_plan.turn_3}</p>
          </div>
        </div>
      </section>
    </div>
  );
}

