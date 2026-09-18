import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

function urlTransform(url: string): string {
  if (url.startsWith("file:")) return "";
  return defaultUrlTransform(url);
}

export default function MarkdownBody({ text }: { text: string }) {
  return (
    <div className="md">
      <Markdown
        remarkPlugins={[remarkGfm]}
        urlTransform={urlTransform}
        components={{
          a: ({ href, children }) =>
            href ? (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            ) : (
              <>{children}</>
            ),
          img: ({ src, alt }) => (src ? <img src={src} alt={alt || ""} /> : null),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
