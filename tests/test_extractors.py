import unittest
from quarry.extractors import extract_referral_codes, extract_code_from_url, is_valid_referral_format


class ExtractionTests(unittest.TestCase):
    def test_rejects_lookalike_and_nested_hosts(self):
        for value in ('https://evilclaude.ai/referral/YWAsr_1fbA',
                      'https://evil.example/claude.ai/referral/YWAsr_1fbA',
                      'https://claude.ai@evil.example/referral/YWAsr_1fbA'):
            with self.subTest(value=value):
                self.assertEqual(extract_referral_codes(value), [])
                self.assertFalse(is_valid_referral_format(value))

    def test_does_not_truncate_identifiers(self):
        code = 'AbCd_' * 8
        self.assertEqual(extract_code_from_url('https://claude.ai/referral/' + code), code)

    def test_rejects_trailing_path_and_invalid_characters(self):
        for value in ('https://claude.ai/referral/ValidCode/extra',
                      'https://claude.ai/referral/ValidCode%2Fextra', 'bad!',
                      'https://claude.ai/referral/2025-01-01',
                      'https://claude.ai/referral/06-14',
                      'https://claude.ai/referral/YYYY-MM-DD'):
            with self.subTest(value=value):
                self.assertFalse(is_valid_referral_format(value))

    def test_preserves_case_and_decodes_transport_entities(self):
        text = 'https:&#x2F;&#x2F;claude.ai&#x2F;referral&#x2F;PFQOnxQmRQ'
        self.assertEqual(extract_referral_codes(text), [('https://claude.ai/referral/PFQOnxQmRQ', 'PFQOnxQmRQ')])
        self.assertNotEqual(extract_code_from_url('AbCdEf'), extract_code_from_url('abcdef'))

    def test_accepts_plain_host_and_query_without_inventing_validity(self):
        self.assertEqual(extract_referral_codes('Use claude.ai/referral/YWAsr_1fbA.'),
                         [('https://claude.ai/referral/YWAsr_1fbA', 'YWAsr_1fbA')])
        self.assertEqual(extract_code_from_url('https://claude.ai/referral/YWAsr_1fbA?utm_source=test'), 'YWAsr_1fbA')

    def test_bad_input_raises_value_error(self):
        for value in ('', None, 'bad!', 'https://other.example/referral/ValidCode'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    extract_code_from_url(value)


    def test_encoded_path_delimiters_do_not_create_different_referrals(self):
        for suffix in ('%3Fnot-the-code', '%23not-the-code', '%253Fnot-the-code'):
            value = 'https://claude.ai/referral/PFQOnxQmRQ' + suffix
            self.assertFalse(is_valid_referral_format(value))
            self.assertEqual(extract_referral_codes(value), [])

    def test_controls_are_rejected_before_urlsplit_can_repair_them(self):
        for control in ('\n', '\r', '\t', '&#10;', '&#9;'):
            value = 'https://clau' + control + 'de.ai/referral/PFQOnxQmRQ'
            self.assertFalse(is_valid_referral_format(value))
            with self.assertRaises(ValueError):
                extract_code_from_url(value)

if __name__ == '__main__':
    unittest.main()
