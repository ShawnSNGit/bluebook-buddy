# The BlueBook Buddy: Accessible Legal Citations for Equal Justice

**The BlueBook Buddy** is a free, offline, dependency-free Python tool designed to bridge the structural divide in legal citation formatting. It finalizes raw, messy research into formatted Bluebook citations while providing dedicated tools for **pro se filers, low-income litigants, Spanish speakers, and disabled individuals using assistive technology**.

---

## Why This Exists: Breaking the Courtroom Gatekeeper

In American courts, hyper-technical citation rules function as an aggressive procedural barrier:
* **The Structural Divide:** High-fee corporate law firms spend tens of thousands of dollars annually on proprietary citation checkers and commercial databases (Westlaw/Lexis). 
* **The Disproportionate Toll:** Pro se filers, first-generation students, working-class litigants, Spanish speakers, and persons with disabilities frequently face clerks striking their pleadings or judges dismissing their claims over minor punctuation, spacing, or citation errors.
* **The Solution:** The BlueBook Buddy provides an open, deterministic, 100% offline, zero-dependency citation engine that levels the playing field—demanding substantive justice over procedural exclusion.

---

## Key Inclusive Capabilities

### 1. Low-Income & Pro Se Litigation Engine (`--pro-se`, `--links`)
* **Zero-Cost Research Integration:** Automatically generates direct, free public research links to [CourtListener / RECAP](https://www.courtlistener.com) (Free Law Project), [Cornell Legal Information Institute (LII)](https://www.law.cornell.edu), and the [Federal Register](https://www.federalregister.gov). Litigants without paid database subscriptions can verify every cited authority for free.
* **Court Docket & Record Standardization:** Recognizes and normalizes handwritten or electronic court record citations (`Doc. 12 at 4` $\to$ `Doc. 12, at 4`, `ECF No. 15, at 2`, `Exhibit A`, `PageID 104`) without penalizing self-represented filers.
* **Demystified Legal Terminology:** Translates arcane citation warnings into plain English (e.g., explaining why a pinpoint page or circuit number is required and how it affects the judge's evaluation).
* **The *Haines v. Kerner* Protective Notice:** Automatically emits the standard pro se protective legal block citing *Haines v. Kerner*, 404 U.S. 519 (1972) and *Erickson v. Pardus*, 551 U.S. 89 (2007), reminding the court that self-represented pleadings must be held to less stringent standards than formal pleadings drafted by attorneys.

### 2. Soporte y Traducción para Hispanohablantes (`--lang es`)
* **Informe de Diagnóstico en Español:** Traduce todas las explicaciones, advertencias, tablas y veredictos a un español claro y accesible (`--lang es`).
* **Normalización de Señales y Términos Legales en Español:** Reconoce y traduce automáticamente términos legales en español a su estándar Bluebook:
  * Señales procesales: *Véase* $\to$ *See*, *Véase también* $\to$ *See also*, *Véase en general* $\to$ *See generally*, *Compare con* $\to$ *Compare*, *Contra* $\to$ *Contra*, *p. ej.* $\to$ *e.g.*
  * Referencias de página: `pág. 153` o `pag. 153` $\to$ `, 153` (pincite estándar).
  * Disposiciones constitucionales: `Constitución de EE. UU. enmienda 14, § 1` $\to$ `U.S. Const. amend. XIV, § 1`.
  * Estatutos federales: `42 Cód. de EE. UU. sección 1983` $\to$ `42 U.S.C. § 1983`.
  * Expedientes judiciales: `Expediente Núm. 4 at 10` $\to$ reconocido y validado.
* **Tabla de Autoridades Bilingüe:** Genera la `TABLA DE AUTORIDADES` con divisiones categorizadas en español (*Casos*, *Estatutos*, *Disposiciones Constitucionales*, *Reglamentos*).

### 3. Assistive Technology & Screen-Reader Optimization (`--a11y`, `--pronounce`)
* **Screen-Reader Mode (`--a11y`):** Removes repetitive ASCII dividers (`===`, `---`) that clutter text-to-speech engines (like NVDA, JAWS, and VoiceOver). Formats reports using semantic Markdown headings (`#`, `##`, `###`) so blind and low-vision filers can jump directly between citations using single-key navigation (`H`).
* **Spoken-Word Pronunciation Guide (`--pronounce`):** Spells out legal citations phonetically into conversational English:
  * *Input:* `Roe v. Wade, 410 U.S. 113, 153 (1973)`
  * *Spoken Guide:* *"Roe versus Wade, Volume 410, United States Reports, page 113, at page 153, decided in 1973."*
  * *Input:* `Smith v. Jones Corp., 123 F.3d 456, 460–61 (2d Cir. 1999)`
  * *Spoken Guide:* *"Smith versus Jones Corp., Volume 123, Federal Reporter, Third Series, page 456, at pages 460 through 61, decided by the Second Circuit Court of Appeals in 1999."*
  * Empowers litigants with visual impairments, speech disabilities, or oral argument anxiety to speak their authorities before judges.
* **Dyslexia-Friendly Plain Text:** Offers high-contrast plain text formatting (`--style plain`) free of asterisks or underlines that can cause visual distortion or braille display errors.

---

## Quick Start

```bash
# 1. Pro Se Mode: Format research, generate free CourtListener/LII links, and include Haines v. Kerner notice
python3 bluebook_buddy.py brief.txt --pro-se

# 2. Modo en Español: Diagnóstico completo y normalización de citas en español
python3 bluebook_buddy.py escrito.txt --lang es

# 3. Accessibility / Screen-Reader Mode: Semantic headings, no ASCII clutter, with pronunciation guide
python3 bluebook_buddy.py brief.txt --a11y --pronounce

# 4. Standard Format with Table of Authorities (Markdown or Plain Text)
python3 bluebook_buddy.py research.txt -o final.md --toa
python3 bluebook_buddy.py research.txt --style plain -o final.txt

# 5. Machine-Readable JSON (Includes free research links & spoken transcripts)
cat notes.txt | python3 bluebook_buddy.py - --json
```

---

## Detailed Flag Reference

| Flag | Purpose | Impact on Vulnerable / Pro Se Filers |
| :--- | :--- | :--- |
| `--pro-se`, `--low-income` | Activates pro se assistance mode | Generates free public links, plain-language rule explanations, and *Haines v. Kerner* notice. |
| `--links`, `--free-links` | Generates free public URLs | Links cases to CourtListener/RECAP, statutes to Cornell LII, and regulations to FederalRegister.gov. |
| `--lang es` | Spanish diagnostic reporting | Translates all diagnostics and notes to Spanish; normalizes Spanish signals and statutory references. |
| `--a11y`, `--screen-reader` | Assistive technology optimization | Generates screen-reader-friendly semantic Markdown without repetitive ASCII art dividers. |
| `--pronounce`, `--speak` | Spoken phonetic guide | Transcribes citations into full spoken English for oral arguments, screen readers, and text-to-speech. |
| `--toa` | Appends Table of Authorities | Groups citations into Cases, Statutes, Constitutions, Regulations, and Rules. |
| `--style` | `markdown`, `underline`, `plain` | Choose between italic markers (`*text*`), underlines (`_text_`), or clean plain text for dyslexia/braille. |
| `--strict` | Fails on warnings (`exit 1`) | Prevents filing submissions until all ambiguous or missing pinpoints are addressed. |

---

## What It Fixes Automatically

1. **Commercial Copy-Paste Residue:** Cleans up messy raw text pasted from Google Scholar, dockets, or legal databases.
2. **Missing Pinpoints & Unclosed Ranges:** Flags missing pincites and standardizes page spans (`1234-1236` $\to$ `1234–36` per Bluebook Rule 3.2).
3. **Reporter & Circuit Spacing:** Fixes spacing anomalies (`F. 3d` $\to$ `F.3d`, `S.Ct.` $\to$ `S. Ct.`, `2nd Cir.` $\to$ `2d Cir.`).
4. **Invalid Signals & "Ibid.":** Replaces prohibited Latin terms like `Ibid.` with `Id.` and normalizes signals (*See, e.g.,*, *Cf.*, *Contra*).
5. **Court Record & Docket Numbers:** Standardizes citations to court dockets (`Doc. 12, at 4`, `ECF No. 15, at 2`).
6. **Spanish Legal Translations:** Automatically maps *Véase*, *Enmienda*, *Cód. de EE. UU.*, and *pág.* to federal Bluebook standards.

---

## Guía Rápida para Hispanohablantes

El BlueBook Buddy está diseñado para ser completamente accesible para personas que presentan documentos en tribunales federales o estatales de EE. UU. y cuyo idioma nativo o preferido es el español:

1. **Ejecución básica en español:**
   ```bash
   python3 bluebook_buddy.py mi_escrito.txt --lang es --pro-se
   ```
2. **Lo que hace el programa:**
   - Detecta si usted escribió `Véase Roe v. Wade` y lo convierte al estándar oficial `See Roe v. Wade`.
   - Si escribió `pág. 45`, lo formatea automáticamente a `, 45`.
   - Si citó la `Constitución de EE. UU. enmienda 14`, lo convierte a `U.S. Const. amend. XIV`.
   - Explica en español sencillo por qué un juez necesita el año o el tribunal sentenciador.
   - Añade el aviso formal de la Corte Suprema en *Haines v. Kerner*, que obliga a los jueces a considerar con indulgencia y flexibilidad los escritos presentados por personas sin abogado.

---

## Accessibility Best Practices (VoiceOver, NVDA, JAWS)

For users who rely on screen readers or refreshable Braille displays:
* Run with `--a11y`:
  ```bash
  python3 bluebook_buddy.py input.txt --a11y --pronounce > report.md
  ```
* Open `report.md` in your preferred Markdown reader or browser. Press `H` to cycle through section headings:
  * `Heading 1`: Title of the report.
  * `Heading 2`: Executive summary and verdict.
  * `Heading 3`: Each individual citation, line by line.
* Use `--style plain` when exporting the formatted brief text to avoid confusing asterisks or underlines on refreshable Braille displays.

---

## Limits (By Design)

* **Form, not substance:** This tool checks citation format, spacing, reporter validity, and rule compliance. It cannot verify whether an authority has been overruled or overturned (shepardized), or that your legal argument is sound.
* **Deterministic and Private:** The tool operates entirely on your local machine. No text is transmitted over the internet, protecting privileged legal research and client confidentiality.
* **Verify Before Filing:** Always double-check your final brief against the specific local rules of your court before formal filing.

---

## Dedication

The BlueBook Buddy is maintained by **Shawn SN** with a steadfast commitment to **protecting the rights of the voiceless and underrepresented as the modern legal landscape evolves**.
