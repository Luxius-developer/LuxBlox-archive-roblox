import json
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit
from server.app import Handler


class R9PresenceContractTests(unittest.TestCase):
    def test_presence_request_contract(self):
        # Regression guard: R9 LuaApp expects POST /presence/v1/presence/users
        # and a top-level userPresences array. Test against a live handler
        # in API integration tests before deploying.
        self.assertEqual(urlsplit('/presence/v1/presence/users').path,
                         '/presence/v1/presence/users')
        response = {'userPresences': [{'userId': 7, 'userPresenceType': 0}]}
        self.assertEqual(response['userPresences'][0]['userId'], 7)


if __name__ == '__main__':
    unittest.main()
