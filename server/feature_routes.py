"""Routes for the LuxBlox social, avatar, settings and place screens."""
import hmac
import json
import re
from urllib.parse import parse_qs
from server import features as f, accounts
from server.errors import ApiError

HTML_HEADERS=[('Content-Type','text/html; charset=utf-8'),('Content-Security-Policy',"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),('Referrer-Policy','no-referrer')]
WEB_PATHS={'/help','/more','/home','/games','/games/1001/Starter-Obby','/games/1001/launch','/feeds/inapp','/develop/landing','/users/friends','/my/friends','/my/avatar','/catalog','/my/inventory','/admin','/my/account/security','/my/account/notifications','/my/account/billing','/my/account/privacy','/premium/membership','/mobile-app-upgrades/native-ios/bc','/upgrades/builderclub'}
ALLOWED_ACTIONS={
 '/admin':{'admin_flags'},'/my/avatar':{'avatar_colors'},'/catalog':{'claim','wear'},'/my/inventory':{'wear'},
 '/my/account/security':{'logout_others'},'/my/account/notifications':{'preferences'},'/my/account/privacy':{'preferences'},
 '/premium/membership':{'premium'},'/mobile-app-upgrades/native-ios/bc':{'premium'},'/upgrades/builderclub':{'premium'}
}


def route(h,path,url,namespace):
    b=h.server.backend;q=parse_qs(url.query);method=h.command
    def reply(status,data=None,headers=()):h.reply(status,data,headers);return True
    def current():return b.current_user(h.cookie_value('.ROBLOSECURITY'))
    if path=='/favicon.ico' and method in ('GET','HEAD'):return reply(204)
    if path=='/checkout/unavailable' and method in ('GET','HEAD','POST'):
        return reply(404,'<!doctype html><html lang="ru"><meta charset="utf-8"><title>404</title><h1>404: не найдено</h1><p>Покупка сейчас недоступна. Деньги не списаны.</p><a href="/more">Вернуться</a></html>'.encode(),HTML_HEADERS)
    if path=='/login' and method in ('GET','POST','HEAD'):
        import secrets
        nonce=h.cookie_value('LUXBLOX-LOGIN') or secrets.token_urlsafe(24)
        token=hmac.new(b.csrf_secret,('login:'+nonce).encode(),'sha256').hexdigest()
        notice='';status=200
        if method=='POST':
            try:
                form=read_form(h)
                if not h.cookie_value('LUXBLOX-LOGIN') or not re.fullmatch(r'[a-f0-9]{64}',form.get('csrf','')) or not hmac.compare_digest(form.get('csrf',''),token):raise ApiError(403,'Откройте страницу входа заново.')
                b.rate_limit(h.client_address[0])
                name=form.get('username','');password=form.get('password','')
                if len(name)>128 or len(password)>128:raise ApiError(400,'Слишком длинные данные.')
                me=b.login(name,password);session=b.session(me['id'])
                return reply(303,headers=[('Location','/more'),('Set-Cookie',h.cookie_header('.ROBLOSECURITY',session,86400))])
            except ApiError as ex:status=ex.status;notice=ex.message
        from html import escape
        html='<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход в LuxBlox</title><style>'+__import__('server.account_pages',fromlist=['STYLE']).STYLE+'</style><main><h1>Вход в LuxBlox</h1><p>'+escape(notice)+'</p><form method="post"><input type="hidden" name="csrf" value="'+token+'"><label>Username<input name="username" required maxlength="20" autocomplete="username"></label><label>Пароль<input type="password" name="password" required maxlength="128" autocomplete="current-password"></label><button>Войти</button></form><p>Используйте аккаунт, созданный в приложении LuxBlox.</p></main></html>'
        return reply(status,html.encode(),HTML_HEADERS+[('Set-Cookie',h.cookie_header('LUXBLOX-LOGIN',nonce,600))])
    match=re.fullmatch(r'/luxblox/avatar/(\d+)\.(svg|png)',path)
    if match and method in ('GET','HEAD'):
        uid=int(match[1]);return reply(200,f.avatar_svg(b,uid) if match[2]=='svg' else f.avatar_png(b,uid),[('Content-Type','image/svg+xml' if match[2]=='svg' else 'image/png')])
    web=path in WEB_PATHS or bool(re.fullmatch(r'/users/\d+/(friends|inventory)',path)) or (bool(re.fullmatch(r'/users/\d+/profile',path)) and 'text/html' in h.headers.get('Accept',''))
    if web and method in ('GET','POST','HEAD'):
        session=h.cookie_value('.ROBLOSECURITY')
        try:me=b.current_user(session)
        except ApiError as ex:
            if ex.status==401 and method in ('GET','HEAD'):return reply(303,headers=[('Location','/login')])
            raise
        uid=me['id'];notice='';status=200
        if path=='/admin' and uid!=b.owner_user_id:raise ApiError(403,'Доступ только владельцу проекта.')
        if method=='POST':
            try:
                form=read_form(h);csrf=accounts.token(b,uid,session)
                if not re.fullmatch(r'[a-f0-9]{64}',form.get('csrf','')) or not hmac.compare_digest(form.get('csrf',''),csrf):raise ApiError(403,'Откройте страницу заново.')
                allowed=ALLOWED_ACTIONS.get(path,set())
                if path in ('/users/friends','/my/friends') or re.fullmatch(r'/users/\d+/friends',path):allowed={'friend_request','friend_accept','friend_decline','friend_unfriend'}
                if re.fullmatch(r'/users/\d+/inventory',path):allowed={'wear'}
                if path in ('/home','/games','/games/1001/Starter-Obby'):allowed={'vote'}
                if form.get('action') not in allowed:raise ApiError(400,'Операция недоступна на этой странице.')
                b.rate_limit_chat(uid);f.mutate(b,uid,session,form)
                return reply(303,headers=[('Location',path+'?saved=1')])
            except ApiError as ex:status=ex.status;notice=ex.message
        elif q.get('saved')==['1']:notice='Изменения сохранены.'
        return reply(status,f.page(b,uid,session,path,q,notice),HTML_HEADERS)
    # Legacy native friends API: exact service namespace prevents catalog collisions.
    if namespace in ('friends','v1'):
        match=re.fullmatch(r'/v1/users/(\d+)/friends(?:/(count|online|statuses))?',path)
        if match and method in ('GET','HEAD'):
            uid=int(match[1]);f.user(b,uid);items=f.friends(b,uid)
            if match[2]=='count':return reply(200,{'count':len(items)})
            if match[2]=='online':return reply(200,{'data':[]})
            if match[2]=='statuses':
                me=current()['id'];ids={str(u['id']) for u in f.friends(b,me)}
                return reply(200,{'data':[{'id':int(i),'status':'Friends' if i in ids else 'NotFriends'} for i in ','.join(q.get('userIds',[])).split(',') if i.isdigit()][:100]})
            return reply(200,{'data':items,'previousPageCursor':None,'nextPageCursor':None})
        if path in ('/v1/my/friends/requests','/v1/user/friend-requests') and method in ('GET','HEAD'):
            return reply(200,{'data':f.requests(b,current()['id']),'previousPageCursor':None,'nextPageCursor':None})
        if path in ('/v1/user/friend-requests/count','/v1/my/friends/requests/count') and method in ('GET','HEAD'):
            return reply(200,{'count':len(f.requests(b,current()['id']))})
        match=re.fullmatch(r'/v1/users/(\d+)/(request-friendship|accept-friend-request|decline-friend-request|unfriend)',path)
        if match and method=='POST':
            uid=current()['id']
            if not h.require_csrf():return True
            b.rate_limit_chat(uid)
            f.friend_action(b,uid,int(match[1]),{'request-friendship':'request','accept-friend-request':'accept','decline-friend-request':'decline','unfriend':'unfriend'}[match[2]])
            return reply(200,{})
    if namespace in ('users','v1'):
        match=re.fullmatch(r'/v1/users/(\d+)',path)
        if match and method in ('GET','HEAD'):return reply(200,f.user(b,int(match[1])))
        if path=='/v1/users/search' and method in ('GET','HEAD'):
            keyword=q.get('keyword',[''])[0][:20]
            if len(keyword)<2:return reply(200,{'data':[],'nextPageCursor':None,'previousPageCursor':None})
            with b.connect() as db:rows=db.execute('SELECT id FROM users WHERE lower(username) LIKE lower(?) ORDER BY id LIMIT 30',('%'+keyword+'%',)).fetchall()
            return reply(200,{'data':[f.user(b,r['id']) for r in rows],'nextPageCursor':None,'previousPageCursor':None})
    if namespace=='avatar' or path in ('/v1/avatar','/v1/avatar/set-body-colors','/v1/avatar-rules'):
        match=re.fullmatch(r'/v1/users/(\d+)/avatar',path)
        if method in ('GET','HEAD') and (path=='/v1/avatar' or match):return reply(200,f.avatar(b,int(match[1]) if match else current()['id']))
        if path=='/v1/avatar/set-body-colors' and method=='POST':
            uid=current()['id']
            if not h.require_csrf():return True
            f.set_avatar(b,uid,h.read_json());return reply(200,{'success':True})
        if path=='/v1/avatar-rules' and method in ('GET','HEAD'):
            return reply(200,{'playerAvatarTypes':['R6'],'scales':{},'wearableAssetTypes':[], 'bodyColorsPalette':[{'brickColorId':i,'hexColor':c[1:],'name':c} for i,c in f.PALETTE.items()], 'minimumDeltaEBodyColorDifference':0,'proportionsAndBodyTypeEnabledForUser':False,'defaultClothingAssetLists':{'defaultShirtAssetIds':[],'defaultPantAssetIds':[]}})
    if namespace=='catalog' and path in ('/v1/search/items/details','/v1/search/items') and method in ('GET','HEAD'):
        return reply(200,{'data':[dict(id=p['id'],name=p['name'],description='Оригинальная одежда Vortix Studio для LuxBlox.',itemType='Asset',assetType=11,creatorType='User',creatorTargetId=b.owner_user_id,creatorName='Vortix Studio',price=0,lowestPrice=0,productId=p['id']) for p in f.SHIRTS],'nextPageCursor':None,'previousPageCursor':None})
    if path=='/luxblox/catalog' and method in ('GET','HEAD'):return reply(200,{'data':f.PRESETS+f.SHIRTS})
    if namespace=='inventory' and method in ('GET','HEAD'):
        match=re.fullmatch(r'/v1/users/(\d+)/can-view-inventory',path)
        if match:return reply(200,{'canView':f.preferences(b,int(match[1]))['inventoryVisible']})
        match=re.fullmatch(r'/v[12]/users/(\d+)/assets/(\d+)',path)
        if match:
            uid=int(match[1]);f.user(b,uid)
            if not f.preferences(b,uid)['inventoryVisible'] and current()['id']!=uid:raise ApiError(403,'Инвентарь закрыт.')
            with b.connect() as db:owned={r['item_id'] for r in db.execute('SELECT item_id FROM catalog_owned WHERE user_id=?',(uid,)).fetchall()}
            return reply(200,{'data':[{'assetId':p['id'],'id':p['id'],'name':p['name'],'assetName':p['name'],'userAssetId':p['id']} for p in f.SHIRTS if p['id'] in owned and int(match[2])==11],'nextPageCursor':None,'previousPageCursor':None})
    if namespace=='avatar' and path=='/v1/avatar/set-wearing-assets' and method=='POST':
        uid=current()['id']
        if not h.require_csrf():return True
        f.wear_assets(b,uid,h.read_json().get('assetIds'));return reply(200,{'success':True})
    if namespace=='economy':
        match=re.fullmatch(r'/v2/assets/(\d+)/details',path)
        if match and method in ('GET','HEAD'):
            item=next((p for p in f.SHIRTS if p['id']==int(match[1])),None)
            if not item:raise ApiError(404,'Предмет не найден.')
            return reply(200,{'AssetId':item['id'],'ProductId':item['id'],'Name':item['name'],'AssetTypeId':11,'PriceInRobux':0,'IsForSale':True,'Creator':{'Id':b.owner_user_id,'Name':'Vortix Studio'}})
        match=re.fullmatch(r'/v1/purchases/products/(\d+)',path)
        if match and method=='POST':
            uid=current()['id']
            if not h.require_csrf():return True
            f.mutate(b,uid,h.cookie_value('.ROBLOSECURITY'),{'action':'claim','item':match[1]})
            return reply(200,{'purchased':True,'reason':'Success','productId':int(match[1])})
    if path in ('/asset','/asset/','/v1/asset') and method in ('GET','HEAD'):
        try:item=int(q.get('id',['0'])[0])
        except ValueError:raise ApiError(400,'Некорректный asset ID.') from None
        shirt=next((p for p in f.SHIRTS if p['id']==item),None)
        if shirt:
            xml='<roblox version="4"><Item class="Shirt" referent="SHIRT"><Properties><string name="Name">LuxBlox Shirt</string><Content name="ShirtTemplate"><url>'+b.public_origin+'/asset/?id='+str(shirt['textureId'])+'</url></Content></Properties></Item></roblox>'
            return reply(200,xml.encode(),[('Content-Type','application/xml')])
        texture=next((p for p in f.SHIRTS if p['textureId']==item),None)
        if texture:return reply(200,(__import__('pathlib').Path(__file__).parent/'static'/('shirt-'+str(texture['id']-6000)+'.png')).read_bytes(),[('Content-Type','image/png')])
        raise ApiError(404,'Ресурс LuxBlox не найден.')
    if namespace=='thumbnails' and path=='/v1/assets' and method in ('GET','HEAD'):
        ids=set(','.join(q.get('assetIds',[])).split(','))
        return reply(200,{'data':[{'targetId':p['id'],'state':'Completed','imageUrl':b.public_origin+'/asset/?id='+str(p['textureId'])} for p in f.SHIRTS if str(p['id']) in ids]})
    if path in ('/Thumbs/Avatar.ashx','/Thumbs/Headshot.ashx') and method in ('GET','HEAD'):
        try:uid=int(q.get('userId',q.get('userid',['0']))[0])
        except ValueError:raise ApiError(400,'Некорректный ID.') from None
        return reply(200,f.avatar_png(b,uid),[('Content-Type','image/png')])
    if namespace=='premiumfeatures' and method in ('GET','HEAD'):
        match=re.fullmatch(r'/v1/users/(\d+)/validate-membership',path)
        if match:return reply(200,f.flags(b,int(match[1]))['isPremium'])
    if namespace=='games':
        match=re.fullmatch(r'/v1/games/(\d+)/votes(?:/user)?',path)
        if match:
            pid=int(match[1])
            if pid!=1001:raise ApiError(404,'Плейс не найден.')
            if method in ('GET','HEAD'):
                data=f.votes(b,pid,current()['id'] if path.endswith('/user') else None)
                return reply(200,{'canVote':True,'userVote':data['userVote'],'reasonForNotVote':''} if path.endswith('/user') else data)
            if method=='PATCH':
                uid=current()['id']
                if not h.require_csrf():return True
                f.set_vote(b,uid,pid,h.read_json().get('isUpVote'));return reply(200,{})
        if path=='/v1/games/votes' and method in ('GET','HEAD'):
            ids=set(','.join(q.get('universeIds',[])).split(','));return reply(200,{'data':[f.votes(b)] if '1001' in ids else []})
    if path in ('/Game/PlaceLauncher.ashx','/v1/join-game-instance','/v1/join-game') and method in ('GET','POST'):
        current();raise ApiError(503,'Игровой сервер LuxBlox не найден. RCC ещё не запущен.')
    return False


def read_form(h):
    if h.headers.get_content_type()!='application/x-www-form-urlencoded' or h.headers.get('Transfer-Encoding'):raise ApiError(415,'Отправьте форму со страницы.')
    try:
        n=int(h.headers.get('Content-Length','0'))
        if not 0<n<=65536:raise ValueError()
        values=parse_qs(h.rfile.read(n).decode(),keep_blank_values=True,max_num_fields=32)
        if any(len(v)!=1 for v in values.values()):raise ValueError()
    except (ValueError,UnicodeDecodeError):raise ApiError(400,'Некорректная форма.') from None
    return {k:v[0] for k,v in values.items()}
