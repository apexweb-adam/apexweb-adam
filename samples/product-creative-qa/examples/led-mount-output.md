## RELEASE_DECISION

REPAIR. The grounded product, use-context, pack, and price claims can ship after the unsupported sensor behavior, battery runtime, and installation-time claims are removed.

## FACT_LOCK

| exact claim element | status | source | release action |
|---|---|---|---|
| “automatic motion sensor” | UNSUPPORTED | NONE | REMOVE OR VERIFY |
| “30 hours of battery life” | UNSUPPORTED | NONE | REMOVE OR VERIFY |
| “installs in 30 seconds” | UNSUPPORTED | NONE | REMOVE OR VERIFY |
| “light to dark closets, cabinets and shelves” | DERIVED | S1 | KEEP |
| “slim rechargeable magnetic no-drill GravN LED Mount” | VERIFIED | S1 | KEEP |
| “duo pack” | VERIFIED | S1 | KEEP |
| “7,990 HUF” | VERIFIED | S1 | KEEP |

## CLAIM_RISK_MATRIX

| exact proposed words | risk class | decision | evidence reason | safe replacement |
|---|---|---|---|---|
| “automatic motion sensor” | product behavior | VERIFY | S2 shows a circular feature but cannot establish its behavior; S3 says sensor behavior was not supplied. | REMOVE OR VERIFY |
| “30 hours of battery life” | quantitative performance | VERIFY | S3 states that no battery runtime was supplied. | “rechargeable light bar” |
| “installs in 30 seconds” | measured installation time | REMOVE | S3 states that no measured installation time was supplied. | “magnetic no-drill placement” |
| “light to dark closets, cabinets and shelves” | intended use | KEEP | S1 supports these use contexts; “dark” describes the proposed context without adding a performance magnitude. | “light for closets, cabinets and shelves” |
| “slim rechargeable magnetic no-drill GravN LED Mount” | product identity and format | KEEP | S1 directly supports each element. | “slim rechargeable GravN LED Mount with magnetic no-drill placement” |
| “duo pack for 7,990 HUF” | pack and price | KEEP | S1 records the duo offer and price. | “duo pack for 7,990 HUF” |

## UNKNOWN_INPUTS

- Product documentation establishing the sensor behavior.
- Valid battery-runtime test evidence and its test conditions.
- Valid installation-time evidence and its test conditions.

## DO_NOT_GENERATE

- Battery-hour, brightness, automatic-sensor behavior, adhesive-strength, installation-time, discount, scarcity, or electrician-comparison claims without new evidence.
- The specific ideas “automatic motion sensor,” “30 hours of battery life,” and “installs in 30 seconds.”

## RELEASE_CHECKLIST

- Every factual claim mapped: PASS
- Unsupported proof excluded: FAIL
- Sensitive claims escalated: PASS
- Price and offer verified: PASS
- Source conflicts resolved: PASS
- Human or legal review still required: NEEDS_REVIEW

