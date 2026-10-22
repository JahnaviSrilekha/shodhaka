import { useRef, useState, type DragEvent } from "react";
import { Icon } from "../../components/Icon";

export const ACCEPT = [".md", ".markdown", ".pdf", ".docx", ".yml", ".yaml", ".properties", "Dockerfile", ".dockerfile"];

export function isSupported(name: string) {
  const lower = name.toLowerCase();
  return lower === "dockerfile" || ACCEPT.some((ext) => ext.startsWith(".") && lower.endsWith(ext));
}

export function Dropzone({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const add = (list: FileList | null) => {
    if (!list) return;
    const byName = new Map(files.map((f) => [f.name, f]));
    Array.from(list).forEach((f) => byName.set(f.name, f));
    onChange([...byName.values()]);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    add(e.dataTransfer.files);
  };

  return (
    <div>
      <div
        className={`dropzone ${over ? "dropzone-over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Add documents"
      >
        <Icon name="upload" size={28} />
        <strong>Drop design docs, policies, ADRs or config files here</strong>
        <span className="muted">or click to choose · Markdown, PDF, Word, YAML, .properties, Dockerfile · up to 10 MB each</span>
        <input ref={input} type="file" multiple hidden data-testid="file-input"
          onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </div>
      {files.length > 0 && (
        <ul className="file-list">
          {files.map((f) => (
            <li key={f.name} className={isSupported(f.name) ? "" : "unsupported"}>
              <Icon name="doc" />
              <span className="file-name">{f.name}</span>
              <span className="muted">{isSupported(f.name) ? `${Math.max(1, Math.round(f.size / 1024))} KB` : "not supported, will be skipped"}</span>
              <button className="icon-button" aria-label={`Remove ${f.name}`} onClick={() => onChange(files.filter((x) => x !== f))}>
                <Icon name="x" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
