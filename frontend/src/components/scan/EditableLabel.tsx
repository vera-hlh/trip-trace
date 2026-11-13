import { useRef, useState } from "react";
import type { MouseEvent } from "react";
import clsx from "clsx";

/** 可内联编辑的文本标签 */
export function EditableLabel({
  value,
  onSave,
  className,
  inputClassName,
}: {
  value: string;
  onSave: (newName: string) => void;
  className?: string;
  inputClassName?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = (e: MouseEvent) => {
    e.stopPropagation();
    setDraft(value);
    setEditing(true);
    setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 10);
  };

  const confirm = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) onSave(trimmed);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value);
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={confirm}
        onKeyDown={(e) => {
          if (e.key === "Enter") confirm();
          if (e.key === "Escape") cancel();
        }}
        onClick={(e) => e.stopPropagation()}
        className={clsx(
          "bg-slate-700 border border-blue-500 rounded px-2 py-0.5 text-sm outline-none",
          inputClassName ?? "w-52 text-white"
        )}
      />
    );
  }

  return (
    <span
      onClick={startEdit}
      title="点击重命名（Enter 确认，Esc 取消）"
      className={clsx(
        "cursor-pointer group inline-flex items-center gap-1",
        className
      )}
    >
      {value}
      <span className="text-slate-600 group-hover:text-slate-400 text-xs transition-colors">
        ✏️
      </span>
    </span>
  );
}
