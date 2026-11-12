import DOMPurify from "dompurify";
import { marked } from "marked";
import { memo, useMemo } from "react";

marked.setOptions({ gfm: true, breaks: true });

// Links in replies open in a new tab and never get access to Kelvo's page.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A") {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

/** Renders a model reply: headings, lists, tables, code, links. HTML from the model is sanitized. */
export const Markdown = memo(function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(text ?? "", { async: false }) as string, { USE_PROFILES: { html: true } }),
    [text],
  );
  return <div className={`md ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
});
