# Product Creative QA sample

A free, bounded release gate from the Apex Product Creative Engine.

It maps every factual element in proposed ecommerce copy to supplied evidence, identifies unsupported claims, and returns a fixed `PASS`, `REPAIR`, or `BLOCK` decision. It does not promise platform approval, legal compliance, or business results.

## Included

- [Copy-ready prompt](./PROMPT.md)
- [Spin Scrubber test input](./examples/spin-scrubber-input.md) and [verified output](./examples/spin-scrubber-output.md)
- [LED Mount test input](./examples/led-mount-input.md) and [verified output](./examples/led-mount-output.md)
- [Contract verifier](./verify-sample.mjs)

## Validation snapshot

| Fixture | Expected decision | Observed decision | Required sections | Contract result |
|---|---:|---:|---:|---:|
| Owned Spin Scrubber | BLOCK | BLOCK | 6/6 | PASS |
| Owned LED Mount | REPAIR | REPAIR | 6/6 | PASS |

Both examples intentionally include unsupported sales claims. The expected behavior is to preserve the grounded offer while refusing invented proof. The fixture outputs were generated in one bounded operator session and checked by the included deterministic verifier. This is product-workflow evidence, not a revenue or return-on-ad-spend claim.

Run the contract check:

```bash
node samples/product-creative-qa/verify-sample.mjs
```

## Full workflow

The complete Product Creative Engine and the six-run proof pack are available on the [product page](https://apexweb.hu/ai-prompt-konyvtar-webshopoknak?utm_source=github&utm_medium=free_sample&utm_campaign=pce_validation) and [private proof page](https://apex-product-creative-engine.judimix.chatgpt.site/?utm_source=github&utm_medium=free_sample&utm_campaign=pce_validation).

