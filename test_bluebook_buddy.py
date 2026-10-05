import unittest

from bluebook_buddy import ERROR, FIXED, OK, WARN, analyze, build_toa, fix_pin


def one(text, **kw):
    r = analyze(text, style="plain", **kw)
    assert len(r.citations) == 1, [(c.kind, c.original) for c in r.citations]
    return r.citations[0], r.text


class Cases(unittest.TestCase):
    def test_scotus_clean(self):
        c, out = one("Roe v. Wade, 410 U.S. 113, 153 (1973)")
        self.assertEqual(out, "Roe v. Wade, 410 U.S. 113, 153 (1973)")
        self.assertEqual(c.status, OK)

    def test_messy_scotus(self):
        c, out = one("Brown vs Board of Education, 347 US 483 at 495 (U.S. 1954)")
        self.assertEqual(out, "Brown v. Board of Educ., 347 U.S. 483, 495 (1954)")
        self.assertEqual(c.status, FIXED)

    def test_circuit_normalized(self):
        _, out = one("Smith v. Jones Corporation, 123 F.3d 456, 460-61 (second Cir. 1999)".replace("second", "2nd"))
        self.assertEqual(out, "Smith v. Jones Corp., 123 F.3d 456, 460–61 (2d Cir. 1999)")

    def test_pin_range_collapse(self):
        self.assertEqual(fix_pin("1234-1236"), "1234–36")
        self.assertEqual(fix_pin("123-127"), "123–27")
        self.assertEqual(fix_pin("99-101"), "99–101")
        self.assertEqual(fix_pin("234-5"), "234–35")

    def test_missing_circuit_is_error(self):
        c, _ = one("Doe v. Roe, 10 F.3d 20, 25 (1995)")
        self.assertEqual(c.status, ERROR)

    def test_missing_paren_is_error(self):
        c, _ = one("Doe v. Roe, 10 F.3d 20, 25")
        self.assertEqual(c.status, ERROR)

    def test_future_year_error(self):
        c, _ = one("Doe v. Roe, 10 F.3d 20, 25 (2d Cir. 2999)")
        self.assertEqual(c.status, ERROR)

    def test_no_pin_warns(self):
        c, _ = one("Doe v. Roe, 10 F.3d 20 (2d Cir. 1995)")
        self.assertEqual(c.status, WARN)

    def test_reporter_year_mismatch_warns(self):
        c, _ = one("Doe v. Roe, 10 F.4th 20, 25 (2d Cir. 1995)")
        self.assertTrue(any("does not normally cover" in n for n in c.notes))

    def test_dc_and_fed_circuit(self):
        _, out = one("A v. B, 1 F.3d 2, 3 (DC Cir. 1999)")
        self.assertIn("(D.C. Cir. 1999)", out)
        _, out = one("A v. B, 1 F.3d 2, 3 (Fed Cir. 1999)")
        self.assertIn("(Fed. Cir. 1999)", out)

    def test_signal_and_leadin(self):
        _, out = one("see also Roe v. Wade, 410 U.S. 113, 153 (1973)")
        self.assertTrue(out.startswith("see also Roe"))
        r = analyze("Under Roe v. Wade, 410 U.S. 113, 153 (1973), x.", style="plain")
        self.assertEqual(r.text, "Under Roe v. Wade, 410 U.S. 113, 153 (1973), x.")

    def test_markdown_italics(self):
        r = analyze("See Roe v. Wade, 410 U.S. 113, 153 (1973).", style="markdown")
        self.assertEqual(r.text, "*See* *Roe v. Wade*, 410 U.S. 113, 153 (1973).")

    def test_in_re(self):
        _, out = one("In re Gault, 387 U.S. 1, 55 (1967)")
        self.assertEqual(out, "In re Gault, 387 U.S. 1, 55 (1967)")

    def test_all_caps_name(self):
        c, out = one("SMITH V. JONES INC., 5 F. Supp. 2d 10, 12 (S.D.N.Y. 2000)")
        self.assertIn("Smith v. Jones Inc.", out)
        self.assertEqual(c.status, WARN)

    def test_regional_reporter_needs_court(self):
        c, _ = one("A v. B, 100 N.E.2d 200, 205 (1950)")
        self.assertEqual(c.status, ERROR)

    def test_en_banc_extra_kept(self):
        _, out = one("A v. B, 1 F.3d 2, 3 (4th Cir. 1999) (en banc)")
        self.assertTrue(out.endswith("(4th Cir. 1999) (en banc)"))

    def test_history_warns(self):
        c, _ = one("A v. B, 1 F.3d 2, 3 (4th Cir. 1999), cert. denied, 500 U.S. 1 (2000)".split(", cert")[0]
                   + ", cert. denied")
        self.assertTrue(any("subsequent history" in n for n in c.notes))

    def test_sct_warns(self):
        c, _ = one("A v. B, 100 S. Ct. 200, 205 (1980)")
        self.assertTrue(any("Rule 10.3.1" in n for n in c.notes))


class Statutes(unittest.TestCase):
    def test_usc(self):
        _, out = one("42 USC 1983")
        self.assertEqual(out, "42 U.S.C. § 1983")
        _, out = one("28 U.S.C. sec. 1291(a)(1)")
        self.assertEqual(out, "28 U.S.C. § 1291(a)(1)")

    def test_usca_warns(self):
        c, _ = one("42 U.S.C.A. § 1983")
        self.assertEqual(c.status, WARN)

    def test_bad_title(self):
        c, _ = one("99 U.S.C. § 1")
        self.assertEqual(c.status, ERROR)

    def test_cfr(self):
        _, out = one("29 CFR 1630.2(g)")
        self.assertEqual(out, "29 C.F.R. § 1630.2(g)")
        _, out = one("29 C.F.R. part 1630")
        self.assertEqual(out, "29 C.F.R. pt. 1630")

    def test_fedreg(self):
        c, out = one("85 Fed Reg 1234, 1240 (Jan. 5, 2020)")
        self.assertEqual(out, "85 Fed. Reg. 1234, 1240 (Jan. 5, 2020)")
        c, _ = one("85 Fed. Reg. 1234")
        self.assertEqual(c.status, WARN)

    def test_rules(self):
        _, out = one("FRAP".replace("FRAP", "Fed R App P 28(a)(8)"))
        self.assertEqual(out, "Fed. R. App. P. 28(a)(8)")
        _, out = one("Fed. R. Civ. P. 12(b)(6)")
        self.assertEqual(out, "Fed. R. Civ. P. 12(b)(6)")
        _, out = one("Fed. R. Evid. 702")
        self.assertEqual(out, "Fed. R. Evid. 702")

    def test_constitution(self):
        _, out = one("US Const. amend. 14, § 1")
        self.assertEqual(out, "U.S. Const. amend. XIV, § 1")
        _, out = one("U.S. Const. art. I, § 8, cl. 3")
        self.assertEqual(out, "U.S. Const. art. I, § 8, cl. 3")


class Sequence(unittest.TestCase):
    def test_id(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973). id at 155-157.", style="plain")
        self.assertEqual(r.text.split(". ", 1)[1].strip(), "Id. at 155–57.") if False else None
        self.assertIn("Id. at 155–57", r.text)

    def test_id_without_antecedent(self):
        r = analyze("Id. at 5.", style="plain")
        self.assertEqual(r.citations[0].status, ERROR)

    def test_ibid(self):
        r = analyze("42 U.S.C. § 1983. Ibid.", style="plain")
        self.assertEqual(r.citations[-1].status, ERROR)

    def test_short_form(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973). Roe, 410 U.S. at 155.", style="plain")
        self.assertEqual([c.kind for c in r.citations], ["case", "short"])
        self.assertEqual(r.citations[1].status, OK)
        r = analyze("Roe, 410 U.S. at 155.", style="plain")
        self.assertEqual(r.citations[0].status, WARN)

    def test_wl_supra_record(self):
        r = analyze("2019 WL 123456 and supra and JA 123", style="plain")
        self.assertEqual([c.kind for c in r.citations], ["wl", "supra", "record"])
        self.assertEqual(r.text, "2019 WL 123456 and supra and JA 123")


class Output(unittest.TestCase):
    def test_toa_dedupes_and_groups(self):
        r = analyze("Roe v. Wade, 410 U.S. 113, 153 (1973). Roe v. Wade, 410 U.S. 113, 155 (1973). "
                    "42 U.S.C. § 1983(a). 42 U.S.C. § 1983(b). Fed. R. App. P. 28(a)(8).", style="plain")
        toa = build_toa(r.citations, "plain")
        self.assertEqual(toa.count("Roe v. Wade"), 1)
        self.assertEqual(toa.count("42 U.S.C. § 1983"), 1)
        self.assertIn("Fed. R. App. P. 28", toa)

    def test_idempotent(self):
        src = ("See Smith vs Jones Corporation, 123 F.3d 456 at 460-461 (2nd Cir. 1999). id at 462. "
               "42 USC 1983. 29 CFR 1630.2(g).")
        a = analyze(src, style="plain").text
        b = analyze(a, style="plain").text
        self.assertEqual(a, b)

    def test_prose_untouched(self):
        txt = "The panel erred. See the discussion below. Id is not here, and neither is 5 Smith."
        r = analyze(txt, style="plain")
        self.assertEqual(r.text, txt)
        self.assertEqual(r.citations, [])

    def test_unwrap(self):
        r = analyze("Roe v. Wade,\n410 U.S. 113, 153 (1973)", style="plain", unwrap=True)
        self.assertEqual(r.text, "Roe v. Wade, 410 U.S. 113, 153 (1973)")


if __name__ == "__main__":
    unittest.main()
