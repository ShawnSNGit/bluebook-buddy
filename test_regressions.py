import unittest

from bluebook_buddy import ERROR, analyze


class Regressions(unittest.TestCase):
    def test_pin_page_number_not_a_party_name(self):
        t = "Id. at 844. Accord Smith v. Acme Insurance Company, 55 F.3d 100, 105 (2nd Cir. 1995)."
        r = analyze(t, style="plain")
        self.assertIn("Accord Smith v. Acme Ins. Co., 55 F.3d 100, 105 (2d Cir. 1995)", r.text)

    def test_acronym_party_not_lowercased(self):
        r = analyze("Chevron USA Inc v. NRDC, 467 U.S. 837, 842 (1984)", style="plain")
        self.assertIn("v. NRDC,", r.text)

    def test_ibid_not_swallowed_into_case_name(self):
        r = analyze("Ibid. See Jones v. Smith, 10 F.3d 20, 21 (2d Cir. 1995).", style="plain")
        self.assertEqual([c.kind for c in r.citations], ["id", "case"])
        self.assertEqual(r.citations[0].status, ERROR)

    def test_pin_with_at_and_no_comma(self):
        r = analyze("Brown vs Board of Education, 347 US 483 at 495 (U.S. 1954)", style="plain")
        self.assertEqual(r.text, "Brown v. Board of Educ., 347 U.S. 483, 495 (1954)")


if __name__ == "__main__":
    unittest.main()


class ProseId(unittest.TestCase):
    def test_lowercase_id_in_prose_untouched(self):
        t = "The court said id. is Latin."
        self.assertEqual(analyze(t, style="plain").text, t)
        r = analyze("42 U.S.C. § 1983. Id. The court agreed. id. at 5.", style="plain")
        self.assertEqual([c.kind for c in r.citations], ["usc", "id", "id"])
