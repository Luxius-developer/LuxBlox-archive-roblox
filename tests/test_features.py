import json
import secrets
import tempfile
import unittest
from pathlib import Path
from server.app import Backend
from server import features as f, accounts, chat
from server.errors import ApiError


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'features.sqlite'
        self.url=__import__('os').getenv('LUXBLOX_FEATURES_POSTGRES_URL')
        self.settings=Path(__file__).parents[1]/'config/AndroidApp.json'
        self.b=Backend(self.path,self.settings,False,database_url=self.url)
        self.addCleanup(self.b.close)
        self.a=self.b.register('O'+secrets.token_hex(6),'owner-password')['id']
        self.c=self.b.register('U'+secrets.token_hex(6),'other-password')['id']
        self.b.owner_user_id=self.a
        self.owner_name=f.user(self.b,self.a)['name']
        self.other_name=f.user(self.b,self.c)['name']
        self.renamed='R'+secrets.token_hex(6)
        self.session=self.b.session(self.a)

    def tearDown(self):self.tmp.cleanup()

    def test_owner_entitlements_are_bound_to_id_and_writes_are_restricted(self):
        with self.assertRaises(ApiError):accounts.mutate(self.b,self.c,'other',{'action':'grant','amount':'10000','request_id':secrets.token_hex(16)})
        with self.assertRaises(ApiError):f.mutate(self.b,self.c,'other',{'action':'admin_flags','target':str(self.c),'verified':'on','premium':'on'})
        f.mutate(self.b,self.a,self.session,{'action':'premium','target':str(self.c)})
        f.mutate(self.b,self.a,self.session,{'action':'admin_flags','target':str(self.c),'verified':'on','premium':'on'})
        self.assertTrue(f.user(self.b,self.c)['hasVerifiedBadge'])
        self.assertTrue(f.user(self.b,self.c)['isPremium'])
        accounts.mutate(self.b,self.a,self.session,{'action':'grant','amount':'800','request_id':secrets.token_hex(16)})
        accounts.mutate(self.b,self.a,self.session,{'action':'username','username':self.renamed,'current_password':'owner-password'})
        new=self.b.register(self.owner_name,'different-password')
        self.assertEqual(self.b.login(self.renamed,'owner-password')['id'],self.a)
        self.assertTrue(f.flags(self.b,self.a)['isOwner'])
        self.assertFalse(f.flags(self.b,new['id'])['isOwner'])
        reopened=Backend(self.path,self.settings,False,database_url=self.url)
        self.addCleanup(reopened.close)
        reopened.owner_user_id=self.a
        self.assertTrue(f.flags(reopened,self.c)['isPremium'])
        self.assertTrue(f.flags(reopened,self.c)['hasVerifiedBadge'])

    def test_premium_gift_resolves_username_and_service_admin_has_no_wallet_grant(self):
        f.mutate(self.b,self.a,self.session,{'action':'premium','username':self.other_name.lower()})
        self.assertTrue(f.flags(self.b,self.c)['isPremium'])
        with self.b.connect() as db:db.execute('INSERT INTO project_admins(user_id) VALUES(?)',(self.c,))
        self.assertTrue(f.is_admin(self.b,self.c))
        f.mutate(self.b,self.c,'qa-session',{'action':'admin_flags','target':str(self.c),'verified':'on'})
        with self.assertRaises(ApiError):accounts.mutate(self.b,self.c,'qa-session',{'action':'grant','amount':'10000','request_id':secrets.token_hex(16)})
        with self.assertRaises(ApiError):f.mutate(self.b,self.c,'qa-session',{'action':'premium','username':self.owner_name})

    def test_friend_request_requires_recipient_acceptance_and_persists(self):
        f.friend_action(self.b,self.a,self.c,'request')
        f.friend_action(self.b,self.a,self.c,'request')
        self.assertEqual(len(f.requests(self.b,self.c)),1)
        with self.assertRaises(ApiError):f.friend_action(self.b,self.a,self.c,'accept')
        f.friend_action(self.b,self.c,self.a,'accept')
        reopened=Backend(self.path,self.settings,False,database_url=self.url)
        self.addCleanup(reopened.close)
        reopened.owner_user_id=self.a
        self.assertEqual(f.friends(reopened,self.a)[0]['id'],self.c)
        self.assertEqual(f.friends(reopened,self.c)[0]['id'],self.a)
        self.assertFalse(f.requests(reopened,self.c))
        f.friend_action(reopened,self.c,self.a,'unfriend')
        self.assertEqual(f.friends(reopened,self.a),[])

    def test_votes_and_inventory_avatar_persist_without_fake_asset_ids(self):
        f.set_vote(self.b,self.a,1001,True);f.set_vote(self.b,self.a,1001,True)
        self.assertTrue(f.votes(self.b,uid=self.a)['userVote'])
        f.set_vote(self.b,self.a,1001,False)
        self.assertFalse(f.votes(self.b,uid=self.a)['userVote'])
        self.assertGreaterEqual(f.votes(self.b)['downVotes'],1)
        before=f.avatar_png(self.b,self.a)
        with self.assertRaises(ApiError):f.mutate(self.b,self.a,self.session,{'action':'wear','item':'9002'})
        f.mutate(self.b,self.a,self.session,{'action':'claim','item':'9002'})
        f.mutate(self.b,self.a,self.session,{'action':'wear','item':'9002'})
        self.assertNotEqual(before,f.avatar_png(self.b,self.a))
        reopened=Backend(self.path,self.settings,False,database_url=self.url)
        self.addCleanup(reopened.close)
        reopened.owner_user_id=self.a
        self.assertEqual(f.avatar(reopened,self.a)['bodyColors']['torsoColorId'],21)
        self.assertEqual(f.avatar(reopened,self.a)['assets'],[])
        self.assertFalse(f.votes(reopened,uid=self.a)['userVote'])
        with self.assertRaises(ApiError):f.set_avatar(self.b,self.a,dict(f.DEFAULT_COLORS,torsoColorId=99999))

    def test_preferences_enforce_message_and_request_privacy(self):
        f.mutate(self.b,self.c,'other',{'action':'preferences'})
        with self.assertRaises(ApiError):f.friend_action(self.b,self.a,self.c,'request')
        with self.assertRaises(ApiError):chat.send(self.b,self.a,self.other_name,'test')
        conv=chat.start_conversation(self.b,self.a,self.c)
        with self.assertRaises(ApiError):chat.send_to_conversation(self.b,conv['id'],self.a,'test')
        self.assertFalse(f.preferences(Backend(self.path,self.settings,False,database_url=self.url),self.c)['inventoryVisible'])
