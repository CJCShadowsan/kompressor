# Browser Extension Design

A browser extension can intercept paste events and replace a large structured paste with decompression instructions plus dense payload text. Browser chat UIs often do not expose a true API-level system/developer instruction field, so the extension must insert instructions directly into the visible chat input.

MVP:

1. Detect JSON/log paste locally.
2. Show a preview and estimated savings.
3. Let the user select a target harness style.
4. Replace the paste only after user approval.
5. Keep all processing local.

Risk: vendor DOM changes may break content-script selectors. API or agent harness adapters remain the preferred integration for reliable instruction placement.
