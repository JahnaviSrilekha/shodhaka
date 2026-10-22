import type { ReactNode } from "react";

export function Breadcrumbs({ items }: { items: { label: ReactNode; href?: string }[] }) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && <span className="crumb-sep" aria-hidden>/</span>}
          {item.href && i < items.length - 1 ? <a href={item.href}>{item.label}</a> : <span aria-current={i === items.length - 1 ? "page" : undefined}>{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}
