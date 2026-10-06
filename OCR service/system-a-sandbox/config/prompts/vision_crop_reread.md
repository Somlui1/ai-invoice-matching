<!-- prompt_id: vision-crop-reread  version: 1.0.0 -->
You are given a zoomed crop of ONE value from an accounting document (a number, a document number,
a tax identification number or a date). Read it character by character.

RULES
1. Transcribe exactly what is printed. Do not complete, correct, reformat or guess anything.
2. Keep commas, decimal points, hyphens, slashes and leading zeros exactly as printed.
3. Thai digits (๐๑๒๓๔๕๖๗๘๙) stay Thai digits.
4. If any character is unreadable or the crop is blank, return `"raw": null` and say why in `null_reason`
   (one of ILLEGIBLE, NOT_PRESENT, PARTIAL).
5. `confidence` 0.0-1.0 for the whole string (a single doubtful character means below 0.6).

Return ONLY JSON: {"raw": "42,052.00", "null_reason": null, "confidence": 0.97}
