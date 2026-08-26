import Link from "next/link";

import styles from "./kinnan-lab.module.css";

const experiments = [
  { name: "DorkMax", note: "+10 mana creatures. Raw speed held, protected conversion fell.", status: "Rejected · 2,000 pairs", tone: styles.rejected },
  { name: "NodeMax", note: "+10 combo/connectivity nodes. Protected T4 fell by 1.65 pp.", status: "Rejected · 2,000 pairs", tone: styles.rejected },
  { name: "Druid + Effigy", note: "Two compact creature-engine variants improved some assembly but not protected conversion.", status: "Rejected · 200 + 2,000", tone: styles.rejected },
  { name: "GSZ + The One Ring", note: "Promising 200-game signal, but the 2k gain did not isolate cleanly to either card.", status: "Retired after isolation", tone: styles.rejected },
  { name: "Shang-Chi packages", note: "More speed and attempts, but protection/resilience costs erased the gain.", status: "Rejected · strict screens", tone: styles.rejected },
  { name: "Hidden + Dramatic", note: "Assembly jumped, but attempts and protected T4 did not follow.", status: "Rejected · 200 pairs", tone: styles.rejected },
  { name: "Cabbage + High Fae", note: "Current-tournament value package lost assembly, attempts, protection, and mulligan quality.", status: "Rejected · 200 pairs", tone: styles.rejected },
];

export default function HomePage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Kinnan cEDH Optimization Lab · August 2026</span>
          <h1>Can we actually build a better 99?</h1>
          <p className={styles.lead}>
            Instead of arguing from decklists alone, this lab puts Kinnan builds through paired Forge/Manabrew games against the same seats, seeds, and adversarial pods. A challenger only replaces the champion when the controlled evidence says it should.
          </p>
          <div className={styles.nav}>
            <a href="#results">See the results</a>
            <a href="#method">How the test works</a>
            <Link href="/auth">Open MagicView</Link>
          </div>
        </div>
        <aside className={styles.heroSide}>
          <div className={styles.champion}>
            <span className={styles.eyebrow}>Current champion</span>
            <strong>F10</strong>
            <p>The best-supported Kinnan 99 so far. No challenger has cleared confirmation strongly enough to replace it.</p>
          </div>
          <div className={styles.pillRow}>
            <span className={styles.pill}>paired canonical seeds</span>
            <span className={styles.pill}>4 seats</span>
            <span className={styles.pill}>4 pod styles</span>
            <span className={styles.pill}>strict validity</span>
          </div>
        </aside>
      </section>

      <section className={styles.section} id="results">
        <div className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Latest strict F10 benchmark</span>
            <h2>The number that matters is protected T4.</h2>
          </div>
          <p>Assembly is useful, but a line that folds to the table is not the goal. The primary endpoint is a deterministic attempt by the end of Kinnan turn four with protection available.</p>
        </div>
        <div className={styles.metrics}>
          <div className={styles.metric}><span>T4 assembly</span><strong>20.25%</strong><small>405 / 2,000</small></div>
          <div className={styles.metric}><span>T4 attempts</span><strong>10.90%</strong><small>218 / 2,000</small></div>
          <div className={styles.metric}><span>Protected T4</span><strong>3.80%</strong><small>76 / 2,000</small></div>
          <div className={styles.metric}><span>Valid games</span><strong>2,000</strong><small>strict control bank</small></div>
        </div>
      </section>

      <section className={styles.section} id="method">
        <div className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>What we are measuring</span>
            <h2>Same game. Different 99.</h2>
          </div>
          <p>Every challenger sees the same canonical game situations as F10. That lets us attribute the difference to the deck change instead of luck from unrelated seats, pods, or opening conditions.</p>
        </div>
        <div className={styles.explainer}>
          <div className={styles.card}><h3>Assembly</h3><p>Did the deck assemble a deterministic combo line by turn four? This measures raw access and connectivity.</p></div>
          <div className={styles.card}><h3>Attempt</h3><p>Could the deck actually move from assembled pieces into a certified deterministic winning attempt?</p></div>
          <div className={styles.card}><h3>Protected attempt</h3><p>The primary endpoint: can Kinnan attempt the win by T4 while also surviving the relevant interaction window?</p></div>
          <div className={styles.card}><h3>Strict validity</h3><p>Incomplete pairs, stale runs, idle timeouts, engine failures, and incompatible cache identities do not count as wins or losses.</p></div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Experiment history</span>
            <h2>Most ideas lose. That is useful.</h2>
          </div>
          <p>The lab starts broad, then narrows. Weak packages are retired after 100–200 paired games; promising ones earn 2,000+ pair confirmation.</p>
        </div>
        <div className={styles.timeline}>
          {experiments.map((experiment) => (
            <article className={styles.experiment} key={experiment.name}>
              <strong>{experiment.name}</strong>
              <div><p>{experiment.note}</p></div>
              <span className={`${styles.status} ${experiment.tone}`}>{experiment.status}</span>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>What the lab has learned</span>
            <h2>Faster is not automatically better.</h2>
          </div>
        </div>
        <div className={styles.explainer}>
          <div className={styles.card}><h3>More dorks ≠ more protected wins</h3><p>DorkMax held assembly but lost protected conversion. Mana density alone did not solve the actual bottleneck.</p></div>
          <div className={styles.card}><h3>More combo nodes can make the deck worse</h3><p>NodeMax produced many nominal lines, but its protected T4 rate dropped decisively.</p></div>
          <div className={styles.card}><h3>Opportunity cost dominates</h3><p>Several new cards looked individually interesting, but the cards removed from F10 were often doing more work than expected.</p></div>
          <div className={styles.card}><h3>Conversion beats raw assembly</h3><p>Hidden Strings + Dramatic Reversal assembled more often, yet failed to turn that speed into more protected attempts.</p></div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <span className={styles.eyebrow}>Next search direction</span>
            <h2>Premium clone + value package.</h2>
          </div>
          <span className={`${styles.status} ${styles.held}`}>Next strict screen</span>
        </div>
        <div className={styles.next}>
          <div className={styles.mutation}>
            <span className={styles.eyebrow}>F10_WAN_CLEVER_VALUE</span>
            <h3>Test flexible clone utility and resilient card advantage without bloating the engine count.</h3>
            <div className={styles.swap}>
              <div><b>OUT</b>Misdirection<br />Nature&apos;s Rhythm</div>
              <div><b>IN</b>Wan Shi Tong, Librarian<br />Clever Impersonator</div>
            </div>
          </div>
          <div className={styles.card}>
            <h3>Promotion rule</h3>
            <p>First: exactly 200 valid paired games. If protected T4 improves credibly, the package earns a fresh 2,000-pair confirmation. Until then, F10 remains the champion.</p>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <strong>This is an experiment log, not a claim that simulation perfectly equals tournament Magic.</strong> Forge/Manabrew is used as a controlled comparison environment; tournament lists and 17Lands are hypothesis-generation inputs, while paired simulation is the promotion gate.
      </footer>
    </main>
  );
}
