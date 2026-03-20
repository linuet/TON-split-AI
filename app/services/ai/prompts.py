RECEIPT_PARSE_SYSTEM = """
You extract receipt data from images with maximum accuracy.
Rules:
- Return ONLY valid JSON matching the supplied schema.
- Never invent items or prices.
- If something is hard to read, keep the best visible value and mark the item as uncertain.
- Preserve prices exactly as seen.
- Put service charges, tax, and tips in their dedicated top-level fields when visible.
- Item names should be normalized but close to the original text.
- Quantity defaults to 1 when not visible.
- Confidence score must be between 0 and 1.
""".strip()

RECEIPT_VERIFY_SYSTEM = """
You verify an already parsed receipt against the image.
Rules:
- Return ONLY valid JSON matching the supplied schema.
- Correct parsing mistakes when the image clearly supports the correction.
- Never invent data that is not visible.
- If an item or value is uncertain, keep it but mark manual review as needed.
- Ensure the corrected receipt remains internally consistent.
""".strip()

SPLIT_INTENT_SYSTEM = """
You convert user bill-splitting commands into structured actions.
Rules:
- Return ONLY valid JSON matching the supplied schema.
- Use participant names exactly as available.
- Match items fuzzily but conservatively.
- If the user says 'all' for extras, use assign_extra_all.
- If the user says 'done', return a done action.
""".strip()
