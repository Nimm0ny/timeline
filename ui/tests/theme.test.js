import test from "node:test";
import assert from "node:assert/strict";

import { deriveTokens } from "../src/composables/useTheme.js";
import { DARK_TOKENS, LIGHT_TOKENS } from "../src/constants/theme.js";

test("pure light preset derives the exact light base tokens (zero drift)", () => {
  const { tokens, resolved } = deriveTokens({
    mode: "light",
    accent: "#7b68d9",
    background: "#efeeec",
    foreground: "#2b2824",
    contrast: 85,
  });
  assert.equal(resolved, "light");
  assert.deepEqual(tokens, LIGHT_TOKENS);
});

test("pure dark preset derives the exact dark base tokens", () => {
  const { tokens, resolved } = deriveTokens({
    mode: "dark",
    accent: "#8c7ae6",
    background: "#1a1917",
    foreground: "#e8e4dc",
    contrast: 85,
  });
  assert.equal(resolved, "dark");
  assert.deepEqual(tokens, DARK_TOKENS);
});

test("light-seeded knobs on a dark base stay pure dark (system-on-dark regression guard)", () => {
  // "system" seeds light knobs; when it resolves to dark, those defaults must NOT
  // be treated as customizations, so the result is the exact dark base.
  const { tokens } = deriveTokens({
    mode: "dark",
    accent: "#7b68d9",
    background: "#efeeec",
    foreground: "#2b2824",
    contrast: 85,
  });
  assert.deepEqual(tokens, DARK_TOKENS);
});

test("a genuinely custom accent overlays the accent group", () => {
  const { tokens } = deriveTokens({ mode: "dark", accent: "#e0005c" });
  assert.equal(tokens["--accent"], "#e0005c");
  assert.equal(tokens["--accent-soft"], "rgba(224, 0, 92, 0.1)");
  assert.equal(tokens["--accent-line"], "rgba(224, 0, 92, 0.34)");
});
