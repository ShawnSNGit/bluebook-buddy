# The BlueBook Buddy

**The BlueBook Buddy** is a free, offline, dependency-free Python tool designed to finalize a messy pile of legal research into formatted, validated citations. 

Nearly 100% of people who try to format Bluebook citations by themselves unintentionally make mistakes that can get their files struck by courts. This disproportionately harms first-generation students, pro se litigants, and low-income filers who don't have access to expensive citation-checking software or paralegal support.

**Disclaimer: This tool is NOT legal advice.** It is simply one of many tools people *can* use to potentially help make their lives easier. Whether you are an attorney, a law review writer, a student, or anyone else, this is a starting point, not a substitute for human review and your own legal judgment.

## Why This Exists (And What It Fixes)

This tool is built on prior work and tailored to catch the most commonly reported Bluebook mistakes found across legal forums and practice:
1. **The "Westlaw/Lexis Copy-Paste" Error:** Copying directly from legal research platforms often includes unnecessary parallel citations (like S. Ct. and L. Ed. 2d) or bad abbreviations. The Buddy strips these out for standard cases.
2. **Missing Pincites:** Every citation needs a pinpoint page unless you're citing a whole case. The Buddy flags missing pinpoints as a `WARN`.
3. **Spacing Errors:** (e.g., `F.3d` vs `F. 3d`, or `S.Ct.` vs `S. Ct.`). The Buddy normalizes all spacing to strict Bluebook Table 1 standards.
4. **Invalid Signals and "Ibid.":** Using "Ibid." instead of "Id." is a classic error. The Buddy flags it and automatically converts `id.` to `Id.` when appropriate. 
5. **Future Years & Missing Circuits:** Catching typos like `2029` instead of `2009`, or forgetting to include the Circuit court in an `F.3d` citation.

## Quick Start

```bash
# Format your research file and output to final.md with a Table of Authorities
python3 bluebook_buddy.py research.txt -o final.md --toa

# Output with underlined citations instead of markdown italics
python3 bluebook_buddy.py research.txt --style underline

# Output a JSON report of all citations and errors
cat notes.txt | python3 bluebook_buddy.py - --json
```

The exit code is `1` if there are any ERRORs (or WARNs if you pass `--strict`), making it perfect for a pre-filing checklist script.

## Customizing Your Buddy (A Step-by-Step Guide)

The BlueBook Buddy is built to be **CUSTOMIZED as a STARTING POINT**. A brief filed in any Supreme Court has vastly different formatting requirements than an article submitted to an academic law journal. Because this is just a single Python file, you can easily tweak it.

Here is how to tailor it in plain English:

### Step 1: Open the file
Open `bluebook_buddy.py` in any text editor (like Notepad, TextEdit, or VS Code).

### Step 2: Change how italics look (Rule 2)
Law journals usually want citations in the footnotes to be mostly plain text or small caps, whereas court briefs want italics (or underlines) for case names and signals.
- Find the `render(s: str, style: str)` function near the top.
- You can change the `"markdown": ("*", "*")` to whatever markup your word processor uses, or change the default style in the argument parser at the bottom.

### Step 3: Tweak the abbreviations (Table T6)
If your specific court requires a strange abbreviation, or you want to add more words to automatically abbreviate in case names:
- Find the `ABBREV = { ... }` dictionary in the code (around line 50).
- Add your own! For example, if you want to always abbreviate "Department" to "Dept." instead of "Dep't", just change `"department": "Dep't"` to `"department": "Dept."`.

### Step 4: Adjust the rules for your jurisdiction
Some state courts require parallel citations to their own state reporters, whereas the Bluebook usually says to just cite the regional reporter.
- If you need to stop the bot from warning you about certain things, search the code for `c.raise_to(WARN` and put a `#` at the beginning of the line to silence that specific warning. 
- For example, if your court *likes* exact dates in parentheticals, find the line `c.raise_to(WARN, "exact date given...")` and delete it or comment it out.

## Limits (By Design)
- **Form, not substance:** It checks form. It cannot confirm a case actually exists, that your pincite is accurate, or that the case hasn't been overturned.
- **Ambiguity = Warning:** If it doesn't know, it throws a warning for you to review manually. It never guesses.
- **Cite-check before filing:** Always manually verify your final document.
