/**
 * Shared top bar — Home | AI-ROUNDTABLE logo | Save & Exit.
 * All chrome in gold (#F5A623). Pass children for a sub-row (breadcrumb etc.).
 */

import React from "react";

/**
 * @param {Object} props
 * @param {function} props.onHome — left HOME button handler (required)
 * @param {function} [props.onSaveExit] — right SAVE & EXIT button handler; renders empty placeholder if omitted
 * @param {React.ReactNode} [props.children] — rendered inside the sticky header, below the top bar
 */
function Header({ onHome, onSaveExit, children }) {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-bg">
      <div className="mx-auto flex h-12 max-w-3xl items-center px-4 sm:px-6">
        <button
          type="button"
          onClick={onHome}
          className="w-24 shrink-0 text-left text-sm font-medium uppercase tracking-wide transition-colors hover:underline focus:outline-none"
          style={{ color: "#F5A623" }}
        >
          Home
        </button>
        <div className="flex flex-1 items-center justify-center">
          <span className="text-[1.1rem] font-semibold uppercase tracking-wide" style={{ color: "#F5A623" }}>
            AI-ROUNDTABLE
          </span>
        </div>
        {onSaveExit ? (
          <button
            type="button"
            onClick={onSaveExit}
            className="w-24 shrink-0 text-right text-sm font-medium uppercase tracking-wide transition-colors hover:underline focus:outline-none"
            style={{ color: "#F5A623" }}
          >
            Save Session
          </button>
        ) : (
          <div className="w-24 shrink-0" aria-hidden />
        )}
      </div>
      {children}
    </header>
  );
}

export default Header;
