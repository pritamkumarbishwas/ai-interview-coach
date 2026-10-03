"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { X } from "lucide-react";

import { cx } from "@/lib/utils";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  className,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
      document.body.style.overflow = "hidden";
    } else if (!open && dialog.open) {
      dialog.close();
      document.body.style.overflow = "";
    }

    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const handleClose = () => {
    onClose();
  };

  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === dialogRef.current) {
      handleClose();
    }
  };

  return (
    <dialog
      ref={dialogRef}
      onClose={handleClose}
      onClick={handleBackdropClick}
      aria-labelledby="modal-title"
      aria-describedby={description ? "modal-desc" : undefined}
      className={cx(
        "backdrop:bg-[#1f2933]/40 backdrop:backdrop-blur-sm",
        "relative z-10 w-full max-w-md overflow-y-auto rounded-2xl bg-card shadow-xl p-0 m-auto animate-rise",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
        <div>
          <h2 id="modal-title" className="text-base font-semibold text-ink">{title}</h2>
          {description ? (
            <p id="modal-desc" className="mt-0.5 text-[13px] text-ink-2">{description}</p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={handleClose}
          className="-m-1.5 rounded-btn p-1.5 text-ink-3 transition-colors hover:bg-mist hover:text-ink-2 focus-visible:outline-2 focus-visible:outline-brand"
          aria-label="Close dialog"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </div>
      <div className="px-6 py-5">{children}</div>
    </dialog>
  );
}
