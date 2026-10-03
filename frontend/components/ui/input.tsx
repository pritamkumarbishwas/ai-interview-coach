"use client";

import {
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
  type TextareaHTMLAttributes,
} from "react";

import { Eye, EyeOff } from "lucide-react";

import { cx } from "@/lib/utils";

export const inputClasses =
  "block w-full rounded-btn border border-line bg-card px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-3 shadow-sm transition-colors focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-100 disabled:bg-mist disabled:text-ink-3";

interface FieldProps {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  optional?: boolean;
  children: ReactNode;
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  optional,
  children,
}: FieldProps) {
  const errorId = htmlFor ? `${htmlFor}-error` : undefined;
  const hintId = htmlFor ? `${htmlFor}-hint` : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[13px] font-medium text-ink">
        {label}
        {required ? (
          <span className="text-danger" aria-hidden="true"> *</span>
        ) : optional ? (
          <span className="font-normal text-ink-3"> (optional)</span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p id={errorId} className="text-xs font-medium text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-ink-3">{hint}</p>
      ) : null}
    </div>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function Input({ invalid, className, ...props }: InputProps) {
  return (
    <input
      className={cx(
        inputClasses,
        invalid && "border-danger focus:border-danger focus:ring-[#fdf0f0]",
        className,
      )}
      {...props}
    />
  );
}

export function PasswordInput({ invalid, className, ...props }: InputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? "text" : "password"}
        className={cx(
          inputClasses,
          "pr-11",
          invalid && "border-danger focus:border-danger focus:ring-[#fdf0f0]",
          className,
        )}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((value) => !value)}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-ink-3 transition-colors hover:text-ink-2"
        aria-label={visible ? "Hide password" : "Show password"}
      >
        {visible ? (
          <EyeOff className="h-4 w-4" aria-hidden />
        ) : (
          <Eye className="h-4 w-4" aria-hidden />
        )}
      </button>
    </div>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
  ref?: Ref<HTMLTextAreaElement>;
}

export function Textarea({
  invalid,
  className,
  ref,
  ...props
}: TextareaProps) {
  return (
    <textarea
      ref={ref}
      className={cx(
        inputClasses,
        "min-h-28 resize-y leading-relaxed",
        invalid && "border-danger focus:border-danger focus:ring-[#fdf0f0]",
        className,
      )}
      {...props}
    />
  );
}
