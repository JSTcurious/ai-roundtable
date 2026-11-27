/**
 * frontend/src/components/SynthesisPanel.test.jsx
 *
 * Renders with the real react-markdown (not a mock) so the test exercises its
 * URL sanitization — a mock that passed hrefs through unchanged hid the bug
 * where citation://n links were blanked to href="".
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import SynthesisPanel, { synthesizerName } from "./SynthesisPanel";

const CITATIONS = [
  "https://example.com/source-1",
  "https://example.com/source-2",
  "https://example.com/source-3",
];

function renderPanel(props) {
  return render(
    <SynthesisPanel isStreaming={false} complete={false} citations={CITATIONS} {...props} />
  );
}

describe("SynthesisPanel citation rendering", () => {
  test("[n] markers link to the matching source URL inside a <sup>", () => {
    renderPanel({ content: "See this claim [1] and also this one [2]." });

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", CITATIONS[0]);
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(links[0].querySelector("sup")).toHaveTextContent("1");
    expect(links[1]).toHaveAttribute("href", CITATIONS[1]);
    expect(links[1].querySelector("sup")).toHaveTextContent("2");
    expect(document.body.textContent).not.toContain("<sup>");
  });

  test("adjacent markers stay separate links", () => {
    renderPanel({ content: "Structured outputs exist [1][3][2]." });

    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      CITATIONS[0],
      CITATIONS[2],
      CITATIONS[1],
    ]);
  });

  test("ordinary markdown links still render alongside citations", () => {
    renderPanel({ content: "A [1] and [docs](https://example.com/docs)." });
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      CITATIONS[0],
      "https://example.com/docs",
    ]);
  });

  test("markers without a matching URL stay literal text", () => {
    renderPanel({ content: "Unmatched marker [9] stays as-is." });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByText(/\[9\]/)).toBeInTheDocument();
  });

  test("no links when the citations array is empty", () => {
    renderPanel({ content: "See this claim [1].", citations: [] });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  test("unsafe protocols are still blanked", () => {
    renderPanel({ content: "[click](javascript:alert(1))", citations: [] });
    const link = screen.getByText("click").closest("a");
    expect(link.getAttribute("href")).toBe("");
  });
});

describe("SynthesisPanel synthesizer label", () => {
  test.each([
    ["claude-opus-4-6", "Claude"],
    ["gpt-5.4", "GPT"],
    ["qwen/qwen-2.5-72b-instruct", "Qwen"],
  ])("%s is labeled %s", (modelId, name) => {
    renderPanel({ content: "Body", modelId });
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(screen.getByText("- Synthesis")).toBeInTheDocument();
  });

  test("unknown or missing model shows a neutral label, never Claude", () => {
    renderPanel({ content: "Body", modelId: "emergency" });
    expect(screen.getByText("Synthesis")).toBeInTheDocument();
    expect(screen.queryByText("Claude")).not.toBeInTheDocument();
  });

  test("synthesizerName maps model IDs to families", () => {
    expect(synthesizerName("claude-sonnet-4-6")).toBe("Claude");
    expect(synthesizerName("GPT-5.4")).toBe("GPT");
    expect(synthesizerName(undefined)).toBeNull();
  });
});
