import unittest
from bluebook_buddy import (
    Citation,
    analyze,
    build_report,
    build_toa,
    get_free_link,
    pronounce_citation,
    HAINES_V_KERNER_NOTICE_EN,
    HAINES_V_KERNER_NOTICE_ES,
    OK,
    FIXED,
    WARN,
    ERROR,
)


class LowIncomeAndProSeTests(unittest.TestCase):
    def test_free_legal_research_links(self):
        # SCOTUS case -> CourtListener link
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973)", style="plain")
        c = r.citations[0]
        self.assertEqual(c.free_link, "https://www.courtlistener.com/c/U.S./410/113/")

        # Federal circuit case -> CourtListener search link
        r = analyze("Smith v. Jones Corp., 123 F.3d 456, 460 (2d Cir. 1999)", style="plain")
        c = r.citations[0]
        self.assertIn("https://www.courtlistener.com/?q=", c.free_link)
        self.assertIn("123+F.3d+456", c.free_link)

        # U.S. Code -> Cornell LII link
        r = analyze("42 U.S.C. § 1983", style="plain")
        c = r.citations[0]
        self.assertEqual(c.free_link, "https://www.law.cornell.edu/uscode/text/42/1983")

        # C.F.R. -> Cornell LII link
        r = analyze("29 C.F.R. § 1630.2", style="plain")
        c = r.citations[0]
        self.assertEqual(c.free_link, "https://www.law.cornell.edu/cfr/text/29/1630.2")

        # Constitution -> Cornell LII link
        r = analyze("U.S. Const. amend. XIV, § 1", style="plain")
        c = r.citations[0]
        self.assertEqual(c.free_link, "https://www.law.cornell.edu/constitution/amendment_xiv")

    def test_pro_se_docket_and_record_normalization(self):
        # Normalize pro se docket citations
        r = analyze("Under Doc. 12 at 4, the defendant admitted liability.", style="plain")
        self.assertEqual([c.kind for c in r.citations], ["record"])
        self.assertIn("Doc. 12, at 4", r.text)

        r2 = analyze("See ECF No. 15 at 2 and Exhibit A.", style="plain")
        self.assertIn("ECF No. 15, at 2", r2.text)

    def test_pro_se_report_with_haines_v_kerner(self):
        r = analyze("Doe v. Roe, 10 F.3d 20 (2d Cir. 1995)", style="plain")
        report = build_report(r.citations, pro_se=True)
        self.assertIn("Haines v. Kerner", report)
        self.assertIn("404 U.S. 519", report)
        self.assertIn("Why this matters", report)
        self.assertIn("https://www.courtlistener.com", report)


class SpanishSpeakerTests(unittest.TestCase):
    def test_spanish_signals(self):
        # 'Véase' translated to 'See'
        r = analyze("Véase Roe v. Wade, 410 U.S. 113, 153 (1973).", style="plain")
        self.assertEqual(len(r.citations), 1)
        self.assertTrue(r.text.startswith("See Roe v. Wade"))
        self.assertTrue(any("Translated Spanish legal signal" in n for n in r.citations[0].notes))

        # 'Véase también' -> 'See also'
        r2 = analyze("Véase también Roe v. Wade, 410 U.S. 113, 153 (1973).", style="plain")
        self.assertTrue(r2.text.startswith("See also Roe v. Wade"))

        # 'Contra' and 'compare con'
        r3 = analyze("Compare con Roe v. Wade, 410 U.S. 113, 153 (1973).", style="plain")
        self.assertTrue(r3.text.startswith("Compare Roe v. Wade"))

    def test_spanish_page_pinpoint(self):
        # 'pág. 153' normalized to comma pinpoint
        r = analyze("Roe v. Wade, 410 U.S. 113, pág. 153 (1973)", style="plain")
        self.assertEqual(r.text, "Roe v. Wade, 410 U.S. 113, 153 (1973)")
        self.assertTrue(any("Normalized Spanish page indicator" in n for n in r.citations[0].notes))

    def test_spanish_constitution_and_statute(self):
        # Constitución de EE. UU. enmienda 14
        r = analyze("Constitución de EE. UU. enmienda 14, § 1", style="plain")
        self.assertEqual(r.text, "U.S. Const. amend. XIV, § 1")

        # Código de EE. UU.
        r2 = analyze("42 Cód. de EE. UU. sección 1983", style="plain")
        self.assertEqual(r2.text, "42 U.S.C. § 1983")

    def test_spanish_report_diagnostics(self):
        r = analyze("Roe v. Wade, 410 U.S. 113 (1973)", style="plain")
        rep = build_report(r.citations, lang="es", pro_se=True)
        self.assertIn("INFORME DE BLUEBOOK BUDDY", rep)
        self.assertIn("ADVERTENCIA", rep)
        self.assertIn("PROTECCIÓN LEGAL PARA LITIGANTES PRO SE", rep)
        self.assertIn("Doctrina Haines v. Kerner", rep)
        self.assertIn("Por qué es importante", rep)

    def test_spanish_table_of_authorities(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973). 42 U.S.C. § 1983.", style="plain")
        toa = build_toa(r.citations, style="plain", lang="es")
        self.assertIn("TABLA DE AUTORIDADES", toa)
        self.assertIn("CASOS", toa)
        self.assertIn("ESTATUTOS", toa)


class AccessibilityAndLessAbledTests(unittest.TestCase):
    def test_spoken_pronunciation_generator(self):
        # Supreme court case
        c_scotus = Citation("case", 0, 35, "Roe v. Wade, 410 U.S. 113, 153 (1973)", "Roe v. Wade, 410 U.S. 113, 153 (1973)")
        pron = pronounce_citation(c_scotus)
        self.assertIn("Roe versus Wade", pron)
        self.assertIn("Volume 410", pron)
        self.assertIn("United States Reports", pron)
        self.assertIn("page 113", pron)
        self.assertIn("at page 153", pron)
        self.assertIn("decided in 1973", pron)

        # Circuit case
        c_circ = Citation("case", 0, 54, "Smith v. Jones Corp., 123 F.3d 456, 460–61 (2d Cir. 1999)", "Smith v. Jones Corp., 123 F.3d 456, 460–61 (2d Cir. 1999)")
        pron2 = pronounce_citation(c_circ)
        self.assertIn("Federal Reporter, Third Series", pron2)
        self.assertIn("Second Circuit Court of Appeals", pron2)
        self.assertIn("pages 460 through 61", pron2)

        # Statute
        c_usc = Citation("usc", 0, 16, "42 U.S.C. § 1983", "42 U.S.C. § 1983")
        self.assertEqual(pronounce_citation(c_usc), "Title 42, United States Code, Section 1983.")

        # Constitution
        c_const = Citation("const", 0, 27, "U.S. Const. amend. XIV, § 1", "U.S. Const. amend. XIV, § 1")
        self.assertIn("Amendment XIV (Fourteen)", pronounce_citation(c_const))

    def test_accessibility_report_structure(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973). Doe v. Roe, 10 F.3d 20 (2d Cir. 1995)", style="plain")
        rep = build_report(r.citations, a11y=True, pronounce=True)
        # Verify semantic headings exist
        self.assertTrue(rep.startswith("# BlueBook Buddy Accessibility Report"))
        self.assertIn("## Executive Summary", rep)
        self.assertIn("## Detailed Citation Analysis", rep)
        self.assertIn("### Citation 1:", rep)
        self.assertIn("Spoken Read-Aloud Guide", rep)
        # Ensure no repetitive ASCII art that disrupts screen readers
        self.assertNotIn("============================================================", rep)
        self.assertNotIn("------------------------------------------------------------", rep)

    def test_accessibility_report_spanish(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973)", style="plain")
        rep = build_report(r.citations, a11y=True, lang="es", pronounce=True)
        self.assertTrue(rep.startswith("# Informe de Accesibilidad de BlueBook Buddy"))
        self.assertIn("## Resumen Ejecutivo", rep)
        self.assertIn("Pronunciación sugerida / Lectura oral", rep)


if __name__ == "__main__":
    unittest.main()
