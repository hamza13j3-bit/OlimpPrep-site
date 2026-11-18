import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

/** Markdown + KaTeX. Raw HTML in the source is not rendered (react-markdown default). */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="prose-statement">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
