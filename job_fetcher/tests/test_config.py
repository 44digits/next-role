import unittest

from job_fetcher.config import ConfigurationError, load_config_json, parse_config


def valid_config():
    return {
        "companies": [
            {
                "name": "Acme",
                "links": [
                    {"label": "Website", "url": "https://acme.example"},
                ],
                "keywords": ["Python", "Django"],
                "keyword_match": "any",
                "locations": ["Remote"],
                "sites": [
                    {
                        "adapter": "example",
                        "url": "https://careers.acme.example/jobs",
                        "search_inputs": {"country": "US"},
                    }
                ],
            }
        ]
    }


class ConfigurationTests(unittest.TestCase):
    def test_parses_company_site_and_optional_search_inputs(self):
        config = parse_config(valid_config())

        self.assertEqual(len(config.companies), 1)
        company = config.companies[0]
        self.assertEqual(company.keyword_match, "any")
        self.assertEqual(company.keywords, ("Python", "Django"))
        self.assertEqual(company.locations, ("Remote",))
        self.assertEqual(company.sites[0].search_inputs, {"country": "US"})
        self.assertEqual(company.sites[0].max_pages, 100)

    def test_search_inputs_may_be_omitted(self):
        payload = valid_config()
        del payload["companies"][0]["sites"][0]["search_inputs"]

        site = parse_config(payload).companies[0].sites[0]

        self.assertEqual(site.search_inputs, {})

    def test_invalid_json_reports_a_configuration_error(self):
        with self.assertRaisesRegex(ConfigurationError, "Invalid JSON"):
            load_config_json('{"companies":')

    def test_empty_company_or_site_lists_are_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "non-empty array"):
            parse_config({"companies": []})

        payload = valid_config()
        payload["companies"][0]["sites"] = []
        with self.assertRaisesRegex(ConfigurationError, "sites must be a non-empty"):
            parse_config(payload)

    def test_invalid_keyword_mode_and_max_pages_are_rejected(self):
        payload = valid_config()
        payload["companies"][0]["keyword_match"] = []
        with self.assertRaisesRegex(ConfigurationError, "keyword_match"):
            parse_config(payload)

        payload = valid_config()
        payload["companies"][0]["sites"][0]["max_pages"] = True
        with self.assertRaisesRegex(ConfigurationError, "max_pages"):
            parse_config(payload)

    def test_unknown_configuration_fields_are_rejected(self):
        payload = valid_config()
        payload["companies"][0]["unexpected"] = True

        with self.assertRaisesRegex(ConfigurationError, "unknown field"):
            parse_config(payload)


if __name__ == "__main__":
    unittest.main()
