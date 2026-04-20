/**
 * frontend/src/components/SynthesisPanel.test.jsx
 *
 * Verifies that [n] citation markers render as clickable superscript anchors,
 * not as raw HTML strings like "<sup>5</sup>".
 *
 * react-markdown v10 is ESM-only and can't be transformed by CRA's Jest config,
 * so we mock it with a minimal shim that delegates markdown link rendering to
 * the components.a prop — which is the exact code path under test.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import SynthesisPanel from "./SynthesisPanel";

// Minimal react-markdown shim: finds [text](href) patterns and calls components.a
// for each one, passing the children and href — identical to what real ReactMarkdown does.
jest.mock("react-markdown", () => {
  return function MockReactMarkdown({ children, components }) {
    const LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;
    const parts = [];
    let last = 0;
    let match;
    let key = 0;

    while ((match = LINK_RE.exec(children)) !== null) {
      if (match.index > last) {
        parts.push(children.slice(last, match.index));
      }
      const [, text, href] = match;
      const A = components?.a;
      parts.push(
        A ? (
          <A key={key++} href={href}>
            {text}
          </A>
        ) : (
          <a key={key++} href={href}>
            {text}
          </a>
        )
      );
      last = match.index + match[0].length;
    }
    if (last < children.length) {
      parts.push(children.slice(last));
    }

    return <div>{parts}</div>;
  };
});

jest.mock("remark-gfm", () => () => {});

const CITATIONS = [
  "https://example.com/source-1",
  "https://example.com/source-2",
];

describe("SynthesisPanel citation rendering", () => {
  test("renders [n] markers as superscript anchor elements, not raw HTML strings", () => {
    render(
      <SynthesisPanel
        content="See this claim [1] and also this one [2]."
        isStreaming={false}
        complete={false}
        citations={CITATIONS}
      />
    );

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);

    // First citation — href points to the resolved URL, not citation://
    const link1 = links[0];
    expect(link1).toHaveAttribute("href", CITATIONS[0]);
    expect(link1).toHaveAttribute("target", "_blank");
    expect(link1).toHaveAttribute("rel", "noopener noreferrer");

    // Must contain a <sup> child, not raw text like "<sup>1</sup>"
    const sup1 = link1.querySelector("sup");
    expect(sup1).not.toBeNull();
    expect(sup1).toHaveTextContent("1");

    // Second citation
    const link2 = links[1];
    expect(link2).toHaveAttribute("href", CITATIONS[1]);
    const sup2 = link2.querySelector("sup");
    expect(sup2).not.toBeNull();
    expect(sup2).toHaveTextContent("2");

    // The literal string "<sup>" must not appear anywhere in the rendered output
    expect(document.body.textContent).not.toContain("<sup>");
  });

  test("leaves [n] markers without a matching URL as literal text", () => {
    render(
      <SynthesisPanel
        content="Unmatched marker [9] stays as-is."
        isStreaming={false}
        complete={false}
        citations={CITATIONS}
      />
    );

    // [9] exceeds the citations array — no anchor should be created
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByText(/\[9\]/)).toBeInTheDocument();
  });

  test("renders no links when citations array is empty", () => {
    render(
      <SynthesisPanel
        content="See this claim [1]."
        isStreaming={false}
        complete={false}
        citations={[]}
      />
    );
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});
