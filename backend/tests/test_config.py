import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.database import build_database_url


class DatabaseConfigTests(unittest.TestCase):
    def test_build_database_url_from_credentials(self):
        url = build_database_url(
            host="localhost",
            port="5432",
            database="gmail_attention",
            username="postgres",
            password="postgres",
        )

        self.assertEqual(
            url,
            "postgresql+psycopg2://postgres:postgres@localhost:5432/gmail_attention",
        )


if __name__ == "__main__":
    unittest.main()
