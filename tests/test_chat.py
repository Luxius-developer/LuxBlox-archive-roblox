from pathlib import Path
import tempfile
import unittest
from server.app import Backend, ApiError
from server import chat,account_pages

class ChatTests(unittest.TestCase):
    def test_private_delivery_storage_validation_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            settings=Path(__file__).parents[1]/'config/AndroidApp.json'
            path=Path(d)/'chat.sqlite3'
            b=Backend(path,settings,False)
            a=b.register('Sender','test-password');r=b.register('Receiver','test-password');other=b.register('Unrelated','test-password')
            message=chat.send(b,a['id'],'receiver','Привет <script>!')
            self.assertEqual(chat.messages(b,a['id'])[0]['id'],message)
            self.assertEqual(chat.messages(b,r['id'])[0]['body'],'Привет <script>!')
            self.assertEqual(chat.messages(b,other['id']),[])
            reopened=Backend(path,settings,False)
            self.assertEqual(chat.messages(reopened,r['id'])[0]['id'],message)
            for recipient,body in [('Missing','hello'),('Sender','hello'),('Receiver',''),('Receiver','x'*501),('Receiver','\x00')]:
                with self.assertRaises(ApiError):chat.send(b,a['id'],recipient,body)
            self.assertEqual(len(chat.messages(b,r['id'])),1)
    def test_wallet_has_no_extra_navigation_and_chat_uses_text_nodes(self):
        page=account_pages.render({'robux':0,'username':'Luxius','displayName':'Luxius'},'csrf',page='robux').decode()
        self.assertNotIn('<nav>',page)
        self.assertIn('createTextNode',chat.render('csrf').decode())
