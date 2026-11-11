import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { Icon } from "./Icon";

export function Field({
  label,
  required,
  error,
  help,
  children,
  htmlFor,
}: {
  label?: string;
  required?: boolean;
  error?: string | string[];
  help?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  const err = Array.isArray(error) ? error.join(" ") : error;
  return (
    <div className="field">
      {label && (
        <label className="label" htmlFor={htmlFor}>
          {label}
          {required && <span className="req">*</span>}
        </label>
      )}
      {children}
      {err ? (
        <div className="field-error">
          <Icon name="alert" size={13} />
          {err}
        </div>
      ) : help ? (
        <div className="help">{help}</div>
      ) : null}
    </div>
  );
}

export function TextInput({
  invalid,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input className={`input ${invalid ? "invalid" : ""} ${className}`} {...props} />;
}

export function SelectInput({
  invalid,
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select className={`select ${invalid ? "invalid" : ""} ${className}`} {...props}>
      {children}
    </select>
  );
}

export function TextArea({
  invalid,
  className = "",
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }) {
  return <textarea className={`textarea ${invalid ? "invalid" : ""} ${className}`} {...props} />;
}

export function Checkbox({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="checkbox-row">
      <input type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  );
}