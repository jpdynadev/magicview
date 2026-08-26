"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth-context";

const experiments = [
  ["More mana", "DorkMax", "More accelerants assembled lines, but did not improve protected turn-four conversion."],
  ["More combo nodes", "NodeMax", "More connectivity actually hurt the primary endpoint. Redundancy alone was not the answer."],
  ["Compact engine", "Druid + Effigy", "A full 2,000-pair test improved raw assembly slightly, but protected attempts still trailed F10."],
  ["Card quality", "The One Ring", "Ring alone slowed assembly and attempts enough that it was rejected after 2,000 paired games."],
];

export default function HomePage() {
  const { user } = useAuth();

  return (
    <main className="lab-landing">
      <nav className="lab-nav">
        <Link className="lab-brand" href="/">MagicView <span>LAB</span></Link>
        <Link className="button secondary" href={user ? "/dashboard" : "/auth"}>
          {user ? "Open dashboard" : "Sign in"}
        </Link>
      </nav>

      <section className="lab-hero">
        <span className="eyebrow">Kinnan cEDH Optimization Lab</span>
        <h1>What if we could play the same opening game <em>thousands</em> of times?</h1>
        <p className="lab-lede">
          We are using real Magic rules in Forge to test Kinnan deck changes against the same seats, pods, draws and random seeds. The goal is not to goldfish the fastest hand. It is to learn which 99 most consistently reaches a <strong>protected deterministic attempt by the end of Kinnan&apos;s turn four.</strong>
        </p>
        <div className="lab-stat-row">
          <div><strong>2,000</strong><span>paired games / deck</span></div>
          <div><strong>4</strong><span>adversarial pod styles</span></div>
          <div><strong>1</strong><span>card can be isolated</span></div>
          <div><strong>0</strong><span>incomplete tests promoted</span></div>
        </div>
      </section>

      <section className="lab-section">
        <span className="eyebrow">The idea, without the engineering</span>
        <h2>Think of it like playtesting with a time machine.</h2>
        <div className="process-grid">
          <article><b>01</b><h3>Start with the champion</h3><p>F10 is our current benchmark 99. Every serious challenger has to beat it on identical game situations.</p></article>
          <article><b>02</b><h3>Change a hypothesis</h3><p>Maybe we need mana, tutors, combo connections, protection, or card quality. We change a package instead of guessing from vibes.</p></article>
          <article><b>03</b><h3>Replay the same worlds</h3><p>Baseline and challenger get the same 2,000 seed + seat + pod keys. That makes the comparison much less noisy.</p></article>
          <article><b>04</b><h3>Ask why, not just who won</h3><p>We track mulligans, assembly, attempts, protection, natural wins, failure reasons and which changed cards were actually seen.</p></article>
        </div>
      </section>

      <section className="lab-section lab-definition">
        <div>
          <span className="eyebrow">Our north-star metric</span>
          <h2>Protected T4 attempt</h2>
        </div>
        <p>A game counts for the primary endpoint when Kinnan has a deterministic winning line assembled and can actually attempt it by the end of turn four with meaningful protection available. Assembly alone is not enough. Having lots of mana is not enough. This distinction is where many of our most interesting results have come from.</p>
      </section>

      <section className="lab-section">
        <span className="eyebrow">What the lab has already taught us</span>
        <h2>Some very reasonable ideas lost.</h2>
        <div className="experiment-grid">
          {experiments.map(([axis, name, result]) => (
            <article key={name} className="experiment-card">
              <span>{axis}</span><h3>{name}</h3><p>{result}</p><div className="retired">RETIRED / NOT PROMOTED</div>
            </article>
          ))}
        </div>
      </section>

      <section className="lab-section lab-now">
        <div>
          <span className="eyebrow">How to read our results</span>
          <h2>We are optimizing a deck, not proving a universal truth about Magic.</h2>
        </div>
        <div className="stack gap-md">
          <p><strong>Forge is the promotion gate.</strong> A serious comparison needs all 2,000 valid unique paired games for both decks. Failed engine games stay separate.</p>
          <p><strong>Context matters.</strong> We split results across balanced, turbo, midrange and mixed adversarial pods and all four Kinnan seats.</p>
          <p><strong>Card telemetry generates the next question.</strong> Seeing a card correlate with wins is interesting; swapping it into the deck and replaying the same games is the actual test.</p>
        </div>
      </section>

      <footer className="lab-footer">
        <div><strong>MagicView Kinnan Lab</strong><p>Iterative, paired, rules-engine cEDH playtesting.</p></div>
        <Link className="button" href={user ? "/dashboard" : "/auth"}>{user ? "Open MagicView" : "Enter MagicView"}</Link>
      </footer>
    </main>
  );
}
