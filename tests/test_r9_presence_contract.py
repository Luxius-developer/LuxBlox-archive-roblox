"""R9 native social response regression tests."""
from pathlib import Path
import tempfile
import unittest
from server.app import Backend
from server import chat


class NativeChatContractTests(unittest.TestCase):
    def test_conversation_metadata_and_activity_order(self):
        with tempfile.TemporaryDirectory() as d:
            settings = Path(__file__).parents[1] / 'config/AndroidApp.json'
            backend = Backend(Path(d) / 'social.sqlite3', settings, False)
            alice = backend.register('AliceR9', 'test-password')
            bob = backend.register('BobR9', 'test-password')
            carol = backend.register('CarolR9', 'test-password')
            ab = chat.start_conversation(backend, alice['id'], bob['id'])
            ac = chat.start_conversation(backend, alice['id'], carol['id'])
            self.assertEqual(chat.conversations(backend, alice['id'])[0]['id'], ac['id'])
            sent = chat.send_to_conversation(backend, ab['id'], alice['id'], 'Привет!')
            latest = chat.conversations(backend, alice['id'])
            self.assertEqual(latest[0]['id'], ab['id'])
            self.assertNotEqual(latest[0]['lastUpdated'], ac['lastUpdated'])
            self.assertEqual(chat.conversation_messages(backend, ab['id'], bob['id'])[0]['messageId'], sent)
            self.assertEqual(latest[0]['conversationType'], 'OneToOneConversation')
            self.assertEqual(len(latest[0]['participants']), 2)


if __name__ == '__main__':
    unittest.main()
