/** Regime label rendered as split-flap tiles. Idea borrowed from split-flap display components;
 *  implemented from scratch in plain CSS (see .flap in globals.css). */
export default function SplitFlap({ text }: { text: string }) {
  return (
    <span className="flap" aria-label={text}>
      {Array.from(text).map((ch, i) => (
        <b key={i} aria-hidden className={ch === " " ? "sp" : undefined} style={{ animationDelay: `${i * 22}ms` }}>
          {ch === " " ? " " : ch}
        </b>
      ))}
    </span>
  );
}
