import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const requiredSections = [
  "## RELEASE_DECISION",
  "## FACT_LOCK",
  "## CLAIM_RISK_MATRIX",
  "## UNKNOWN_INPUTS",
  "## DO_NOT_GENERATE",
  "## RELEASE_CHECKLIST",
];

const fixtures = [
  {
    name: "spin-scrubber",
    decision: "BLOCK",
    riskyClaims: [
      "Cuts your cleaning time in half",
      "removes 99.9% of germs",
      "is fully waterproof",
      "is loved by thousands",
    ],
  },
  {
    name: "led-mount",
    decision: "REPAIR",
    riskyClaims: [
      "automatic motion sensor",
      "30 hours of battery life",
      "installs in 30 seconds",
    ],
  },
];

const prompt = await readFile(join(root, "PROMPT.md"), "utf8");
assert.match(prompt, /Return exactly these six sections/);
assert.doesNotMatch(prompt, /PCE-\d{2}/, "The free prompt must not expose paid workflow prompt identifiers.");

const results = [];

for (const fixture of fixtures) {
  const input = await readFile(join(root, "examples", `${fixture.name}-input.md`), "utf8");
  const output = await readFile(join(root, "examples", `${fixture.name}-output.md`), "utf8");

  for (const section of requiredSections) {
    assert.equal(
      output.split(section).length - 1,
      1,
      `${fixture.name}: ${section} must occur exactly once.`,
    );
  }

  assert.match(
    output,
    new RegExp(`## RELEASE_DECISION\\s+${fixture.decision}\\.`),
    `${fixture.name}: expected ${fixture.decision}.`,
  );

  for (const riskyClaim of fixture.riskyClaims) {
    assert.ok(input.includes(riskyClaim), `${fixture.name}: risky claim missing from input.`);
    assert.ok(output.includes(riskyClaim), `${fixture.name}: risky claim missing from audit output.`);
  }

  assert.match(output, /- Every factual claim mapped: PASS/);
  assert.match(output, /- Price and offer verified: PASS/);
  assert.match(output, /REMOVE|VERIFY/);

  results.push({
    fixture: fixture.name,
    expectedDecision: fixture.decision,
    observedDecision: fixture.decision,
    requiredSections: `${requiredSections.length}/${requiredSections.length}`,
    result: "PASS",
  });
}

const promptSha256 = createHash("sha256").update(prompt).digest("hex");

console.log(JSON.stringify({
  sample: "product-creative-qa",
  promptSha256,
  fixtures: results,
  failures: 0,
}, null, 2));
