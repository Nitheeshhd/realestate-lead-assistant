export function Skeleton({ h = 90, n = 1 }) {
  return Array.from({ length: n }).map((_, i) => <div key={i} className="skel" style={{ height: h }} aria-hidden="true" />);
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state" role="alert">
      <b>We couldn't load this.</b>
      <p>{message}</p>
      {onRetry && <button className="btn" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Empty({ title, children }) {
  return <div className="state"><b>{title}</b>{children && <p>{children}</p>}</div>;
}

export function Pill({ children, tone }) {
  return <span className={`pill ${tone || ""}`}>{children}</span>;
}

export function Field({ label, children }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}
