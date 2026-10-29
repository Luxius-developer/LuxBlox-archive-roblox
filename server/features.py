"""Persistent social features and original avatar presets for LuxBlox."""
import hashlib
import hmac
import json
import re
import time
from html import escape
from urllib.parse import parse_qs
from server import accounts
from server.errors import ApiError
from server.account_pages import STYLE

DEFAULT_COLORS = dict(headColorId=24, torsoColorId=23, leftArmColorId=24,
                      rightArmColorId=24, leftLegColorId=119, rightLegColorId=119)
PALETTE = {24:'#f5cd30',23:'#0d69ac',119:'#a4bd47',1:'#f2f3f3',26:'#1b2a35',21:'#c4281c',28:'#287f47'}
PRESETS = [dict(id=9001,name='Классический',torso=23,legs=119),
           dict(id=9002,name='Красный исследователь',torso=21,legs=26),
           dict(id=9003,name='Зелёный строитель',torso=28,legs=1)]
SHIRTS = [dict(id=6001+i,name=name,assetType=11,textureId=7001+i,color=color) for i,(name,color) in enumerate([('Синяя клетка LuxBlox',23),('Красная клетка LuxBlox',21),('Зелёная клетка LuxBlox',28)])]
PREFS = {'friendRequestsEnabled':True,'messagesEnabled':True,'friendNotifications':True,'messageNotifications':True,'inventoryVisible':True}


def initialize(db):
    for sql in [
        '''CREATE TABLE IF NOT EXISTS avatar_worn(user_id BIGINT NOT NULL REFERENCES users(id),item_id INTEGER NOT NULL,PRIMARY KEY(user_id,item_id))''',
        '''CREATE TABLE IF NOT EXISTS project_flags(user_id BIGINT PRIMARY KEY REFERENCES users(id),premium INTEGER NOT NULL DEFAULT 0,verified INTEGER NOT NULL DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS social_requests(sender BIGINT NOT NULL REFERENCES users(id),recipient BIGINT NOT NULL REFERENCES users(id),created_at BIGINT NOT NULL,PRIMARY KEY(sender,recipient),CHECK(sender<>recipient))''',
        '''CREATE TABLE IF NOT EXISTS social_friends(low_id BIGINT NOT NULL REFERENCES users(id),high_id BIGINT NOT NULL REFERENCES users(id),PRIMARY KEY(low_id,high_id),CHECK(low_id<high_id))''',
        '''CREATE TABLE IF NOT EXISTS avatar_profiles(user_id BIGINT PRIMARY KEY REFERENCES users(id),colors TEXT NOT NULL,preset_id INTEGER NOT NULL DEFAULT 9001)''',
        '''CREATE TABLE IF NOT EXISTS catalog_owned(user_id BIGINT NOT NULL REFERENCES users(id),item_id INTEGER NOT NULL,PRIMARY KEY(user_id,item_id))''',
        '''CREATE TABLE IF NOT EXISTS place_votes(user_id BIGINT NOT NULL REFERENCES users(id),place_id BIGINT NOT NULL,vote INTEGER NOT NULL CHECK(vote IN(-1,1)),PRIMARY KEY(user_id,place_id))''',
        '''CREATE TABLE IF NOT EXISTS user_preferences(user_id BIGINT PRIMARY KEY REFERENCES users(id),settings TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS admin_audit(actor BIGINT NOT NULL,target BIGINT NOT NULL,action TEXT NOT NULL,created_at BIGINT NOT NULL)'''
    ]: db.execute(sql)


def flags(backend, uid):
    with backend.connect() as db:
        r=db.execute('SELECT premium,verified FROM project_flags WHERE user_id=?',(uid,)).fetchone()
    return {'isPremium':bool(r and r['premium']),'hasVerifiedBadge':bool(r and r['verified']), 'isOwner':uid==backend.owner_user_id}


def user(backend, uid):
    with backend.connect() as db:
        r=db.execute('''SELECT u.id,u.username,p.display_name FROM users u LEFT JOIN account_profiles p ON p.user_id=u.id WHERE u.id=?''',(uid,)).fetchone()
    if not r: raise ApiError(404,'Пользователь не найден.')
    return dict(id=r['id'],name=r['username'],displayName=r['display_name'] or r['username'],**flags(backend,uid))


def preferences(backend, uid):
    with backend.connect() as db:r=db.execute('SELECT settings FROM user_preferences WHERE user_id=?',(uid,)).fetchone()
    return dict(PREFS,**(json.loads(r['settings']) if r else {}))


def friends(backend, uid):
    with backend.connect() as db:
        rows=db.execute('SELECT low_id,high_id FROM social_friends WHERE low_id=? OR high_id=?',(uid,uid)).fetchall()
    return [user(backend,r['high_id'] if r['low_id']==uid else r['low_id']) for r in rows]


def requests(backend, uid):
    with backend.connect() as db:rows=db.execute('SELECT sender FROM social_requests WHERE recipient=? ORDER BY created_at DESC LIMIT 100',(uid,)).fetchall()
    return [dict(user(backend,r['sender']),friendRequest={'sentAt':'','senderId':r['sender']}) for r in rows]


def friend_action(backend, uid, target, action):
    try: target=int(target)
    except (ValueError,TypeError):raise ApiError(400,'Некорректный ID пользователя.') from None
    user(backend,target)
    if uid==target:raise ApiError(400,'Нельзя добавить себя.')
    low,high=sorted((uid,target))
    if action=='request' and not preferences(backend,target)['friendRequestsEnabled']:raise ApiError(403,'Пользователь отключил заявки.')
    with backend.connect() as db:
        if not backend.is_postgres:db.execute('BEGIN IMMEDIATE')
        if action=='request':
            if not db.execute('SELECT 1 FROM social_friends WHERE low_id=? AND high_id=?',(low,high)).fetchone():
                db.execute('INSERT INTO social_requests(sender,recipient,created_at) VALUES(?,?,?) ON CONFLICT(sender,recipient) DO NOTHING',(uid,target,int(time.time())))
        elif action=='accept':
            if not db.execute('SELECT 1 FROM social_requests WHERE sender=? AND recipient=?',(target,uid)).fetchone():raise ApiError(409,'Входящей заявки нет.')
            db.execute('INSERT INTO social_friends(low_id,high_id) VALUES(?,?) ON CONFLICT(low_id,high_id) DO NOTHING',(low,high))
            db.execute('DELETE FROM social_requests WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)',(uid,target,target,uid))
        elif action=='decline':db.execute('DELETE FROM social_requests WHERE sender=? AND recipient=?',(target,uid))
        elif action=='unfriend':db.execute('DELETE FROM social_friends WHERE low_id=? AND high_id=?',(low,high))
        else:raise ApiError(400,'Неизвестная операция.')


def avatar(backend, uid):
    user(backend,uid)
    with backend.connect() as db:r=db.execute('SELECT colors,preset_id FROM avatar_profiles WHERE user_id=?',(uid,)).fetchone()
    with backend.connect() as db:worn={x['item_id'] for x in db.execute('SELECT item_id FROM avatar_worn WHERE user_id=?',(uid,)).fetchall()}
    assets=[{'id':p['id'],'name':p['name'],'assetType':{'id':11,'name':'Shirt'},'currentVersionId':p['id']} for p in SHIRTS if p['id'] in worn]
    return {'scales':{'height':1,'width':1,'head':1,'depth':1,'proportion':0,'bodyType':0},'playerAvatarType':'R6',
            'bodyColors':json.loads(r['colors']) if r else DEFAULT_COLORS.copy(),'assets':assets,'emotes':[], 'presetId':r['preset_id'] if r else 9001}


def set_avatar(backend,uid,colors,preset=9001):
    if not isinstance(colors,dict) or set(colors)!=set(DEFAULT_COLORS) or any(type(v)!=int or v not in PALETTE for v in colors.values()):raise ApiError(400,'Выберите цвет из доступной палитры.')
    with backend.connect() as db:db.execute('''INSERT INTO avatar_profiles(user_id,colors,preset_id) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET colors=excluded.colors,preset_id=excluded.preset_id''',(uid,json.dumps(colors),preset))


def votes(backend,pid=1001,uid=None):
    with backend.connect() as db:
        rows=db.execute('SELECT vote,COUNT(*) AS n FROM place_votes WHERE place_id=? GROUP BY vote',(pid,)).fetchall()
        own=db.execute('SELECT vote FROM place_votes WHERE user_id=? AND place_id=?',(uid,pid)).fetchone() if uid else None
    counts={r['vote']:r['n'] for r in rows}
    return {'id':pid,'upVotes':counts.get(1,0),'downVotes':counts.get(-1,0),'userVote':None if not own else own['vote']==1}


def set_vote(backend,uid,pid,vote):
    if pid!=1001:raise ApiError(404,'Плейс не найден.')
    if type(vote)!=bool:raise ApiError(400,'isUpVote должен быть true или false.')
    with backend.connect() as db:db.execute('INSERT INTO place_votes(user_id,place_id,vote) VALUES(?,?,?) ON CONFLICT(user_id,place_id) DO UPDATE SET vote=excluded.vote',(uid,pid,1 if vote else -1))


def avatar_svg(backend,uid):
    c={k:PALETTE[v] for k,v in avatar(backend,uid)['bodyColors'].items()}
    rects=[(84,16,72,66,'headColorId'),(66,86,108,106,'torsoColorId'),(25,86,36,106,'leftArmColorId'),(179,86,36,106,'rightArmColorId'),(66,198,51,92,'leftLegColorId'),(123,198,51,92,'rightLegColorId')]
    s='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="310" viewBox="0 0 240 310"><rect width="240" height="310" fill="#f2f4f5"/>'
    s+=''.join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{c[key]}" stroke="#555" stroke-width="2"/>' for x,y,w,h,key in rects)
    return (s+'<circle cx="106" cy="41" r="3"/><circle cx="134" cy="41" r="3"/><path d="M104 56 Q120 68 136 56" fill="none" stroke="#333" stroke-width="3"/></svg>').encode()


def mutate(backend,uid,session,form):
    action=form.get('action','')
    if action.startswith('friend_'):
        target=form.get('target','')
        if not target.isdigit():
            with backend.connect() as db:r=db.execute('SELECT id FROM users WHERE lower(username)=lower(?)',(target,)).fetchone()
            if not r:raise ApiError(404,'Пользователь не найден.')
            target=r['id']
        friend_action(backend,uid,target,action[7:]);return
    if action=='vote':set_vote(backend,uid,1001,form.get('vote')=='up');return
    if action in ('claim','wear'):
        try:item=int(form.get('item',''))
        except ValueError:raise ApiError(400,'Некорректный предмет.') from None
        p=next((p for p in PRESETS+SHIRTS if p['id']==item),None)
        if not p:raise ApiError(404,'Предмет не найден.')
        with backend.connect() as db:
            if action=='wear' and not db.execute('SELECT 1 FROM catalog_owned WHERE user_id=? AND item_id=?',(uid,item)).fetchone():raise ApiError(403,'Сначала получите этот комплект.')
            db.execute('INSERT INTO catalog_owned(user_id,item_id) VALUES(?,?) ON CONFLICT(user_id,item_id) DO NOTHING',(uid,item))
        if action=='wear':
            if item>=9000:set_avatar(backend,uid,dict(DEFAULT_COLORS,torsoColorId=p['torso'],leftLegColorId=p['legs'],rightLegColorId=p['legs']),item)
            else:wear_assets(backend,uid,[item])
        return
    if action=='avatar_colors':
        try:colors={k:int(form.get(k,'')) for k in DEFAULT_COLORS}
        except (ValueError,TypeError):raise ApiError(400,'Некорректный цвет.') from None
        set_avatar(backend,uid,colors);return
    if action=='preferences':
        prefs={key:form.get(key)=='on' for key in PREFS}
        with backend.connect() as db:db.execute('INSERT INTO user_preferences(user_id,settings) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET settings=excluded.settings',(uid,json.dumps(prefs)))
        return
    if action=='logout_others':
        with backend.connect() as db:db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,hashlib.sha256(session.encode()).hexdigest()))
        return
    if action in ('premium','admin_flags'):
        if uid!=backend.owner_user_id:raise ApiError(403,'Доступ только владельцу проекта.')
        try:target=int(form.get('target',uid))
        except ValueError:raise ApiError(400,'Некорректный пользователь.') from None
        user(backend,target)
        premium=int(form.get('premium')=='on') if action=='admin_flags' else 1
        verified=int(form.get('verified')=='on')
        with backend.connect() as db:
            if action=='premium':db.execute('INSERT INTO project_flags(user_id,premium) VALUES(?,1) ON CONFLICT(user_id) DO UPDATE SET premium=1',(target,))
            else:db.execute('INSERT INTO project_flags(user_id,premium,verified) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET premium=excluded.premium,verified=excluded.verified',(target,premium,verified))
            db.execute('INSERT INTO admin_audit(actor,target,action,created_at) VALUES(?,?,?,?)',(uid,target,action,int(time.time())))
        return
    raise ApiError(400,'Неизвестная операция.')


def page(backend,uid,session,path,query,notice=''):
    e=lambda v:escape(str(v),quote=True)
    csrf=accounts.token(backend,uid,session)
    me=user(backend,uid)
    def form(action,body):return '<form method="post"><input type="hidden" name="csrf" value="'+csrf+'"><input type="hidden" name="action" value="'+action+'">'+body+'</form>'
    def badge(u):return e(u['displayName'])+(' <span class="badge" title="Подтверждён в LuxBlox">✓</span>' if u['hasVerifiedBadge'] else '')
    admin=uid==backend.owner_user_id
    nav='<nav class="tabs">'+''.join('<a href="'+url+'">'+name+'</a>' for name,url in [('Главная','/home'),('Игры','/games'),('Друзья','/users/friends'),('Аватар','/my/avatar'),('Каталог','/catalog'),('Инвентарь','/my/inventory'),('Чат','/my/messages'),('Ещё','/more')])+'</nav>'
    title='LuxBlox';body=''
    if path in ('/more','/help'):
        title='Ещё' if path=='/more' else 'Справка и разделы LuxBlox'
        links=[('Информация об аккаунте','/my/account'),('Безопасность','/my/account/security'),('Уведомления','/my/account/notifications'),('Оплата','/my/account/billing'),('Robux','/upgrades/robux'),('Premium','/premium/membership'),('Сведения','/info/about'),('Справка','/help')]
        if admin:links.append(('Админ-панель','/admin'))
        body='<section>'+''.join('<p><a href="'+u+'">'+n+' →</a></p>' for n,u in links)+'</section>'
    elif path in ('/home','/games','/develop/landing','/feeds/inapp') or path.startswith('/games/1001'):
        title='Игры' if path=='/games' else 'Главная'
        v=votes(backend,uid=uid)
        body='<section><h2>'+badge(me)+'</h2><p>'+('Premium' if me['isPremium'] else 'Добро пожаловать в LuxBlox')+'</p></section>'
        body+='<section><img class="cover" src="/static/place-1001.png" alt="Мини-обби"><h2>LuxBlox Starter Obby</h2><p>Старт, десять платформ и финиш. Vortix Studio.</p><p>👍 '+str(v['upVotes'])+' · 👎 '+str(v['downVotes'])+'</p>'
        body+=form('vote','<input type="hidden" name="vote" value="up"><button>Нравится</button>')+form('vote','<input type="hidden" name="vote" value="down"><button class="secondary">Не нравится</button>')
        body+='<p><a class="play" href="/games/1001/launch">Играть</a></p><p class="muted">Игровой сервер сейчас недоступен.</p></section>'
        if path.endswith('/launch'):
            title='Соединение прервано'
            body='<section role="alert"><h2>Соединение прервано</h2><p>Сервер не найден. Игровой сервер LuxBlox ещё не запущен.</p><p class="muted">Это сообщение страницы LuxBlox; соединения с игровым движком не было.</p><a href="/games">Вернуться к играм</a></section>'
    elif path in ('/users/friends','/my/friends') or re.fullmatch(r'/users/\d+/friends',path):
        title='Друзья'
        body='<section><h2>Добавить друга</h2>'+form('friend_request','<label>Username<input name="target" required maxlength="20"></label><button>Отправить заявку</button>')+'</section><section><h2>Входящие заявки</h2>'
        for u in requests(backend,uid):
            body+='<p>'+badge(u)+'</p>'+form('friend_accept','<input type="hidden" name="target" value="'+str(u['id'])+'"><button>Принять</button>')+form('friend_decline','<input type="hidden" name="target" value="'+str(u['id'])+'"><button class="secondary">Отклонить</button>')
        body+='</section><section><h2>Мои друзья</h2>'
        for u in friends(backend,uid):body+='<p>'+badge(u)+'</p>'+form('friend_unfriend','<input type="hidden" name="target" value="'+str(u['id'])+'"><button class="secondary">Удалить из друзей</button>')
        body+='</section>'
    elif path in ('/catalog','/my/inventory') or re.fullmatch(r'/users/\d+/inventory',path):
        is_catalog=path=='/catalog';title='Каталог' if is_catalog else 'Инвентарь'
        target=int(path.split('/')[2]) if path.startswith('/users/') else uid
        user(backend,target)
        if target!=uid and not preferences(backend,target)['inventoryVisible']:raise ApiError(403,'Инвентарь закрыт.')
        with backend.connect() as db:owned={r['item_id'] for r in db.execute('SELECT item_id FROM catalog_owned WHERE user_id=?',(target,)).fetchall()}
        body='<p>Бесплатные комплекты цветов и оригинальные рубашки LuxBlox для классического R6.</p>'
        for p in PRESETS+SHIRTS:
            if not is_catalog and p['id'] not in owned:continue
            body+='<section><h2>'+e(p['name'])+'</h2><p>Бесплатно · Vortix Studio</p>'
            if target==uid:body+=form('wear' if p['id'] in owned else 'claim','<input type="hidden" name="item" value="'+str(p['id'])+'"><button>'+('Надеть' if p['id'] in owned else 'Получить')+'</button>')
            body+='</section>'
        if not is_catalog and not owned:body+='<p>Инвентарь пока пуст. <a href="/catalog">Выбрать комплект</a></p>'
    elif path=='/my/avatar':
        title='Редактор аватара';a=avatar(backend,uid)
        body='<section><img class="avatar" src="/luxblox/avatar/'+str(uid)+'.svg" alt="Мой персонаж R6"><p>Классический R6 · цвета сохраняются в аккаунте.</p>'
        labels=['Голова','Тело','Левая рука','Правая рука','Левая нога','Правая нога']
        options=''
        for key,label in zip(DEFAULT_COLORS,labels):
            options+='<label>'+label+'<select name="'+key+'">'+''.join('<option value="'+str(k)+'"'+(' selected' if a['bodyColors'][key]==k else '')+'>'+v+'</option>' for k,v in PALETTE.items())+'</select></label>'
        body+=form('avatar_colors',options+'<button>Сохранить аватар</button>')+'</section><p><a href="/my/inventory">Мои комплекты</a> · <a href="/catalog">Каталог</a></p>'
    elif path in ('/premium/membership','/mobile-app-upgrades/native-ios/bc','/upgrades/builderclub'):
        title='LuxBlox Premium';body='<section><h2>'+('Premium активен' if me['isPremium'] else 'Premium')+'</h2><p>Статус сохраняется в аккаунте. Дополнительных игровых преимуществ пока нет.</p>'
        if admin:body+=form('premium','<button>Активировать бесплатно для себя</button>')+form('premium','<label>ID получателя подарка<input name="target" type="number" min="1" required></label><button>Подарить Premium</button>')
        else:body+='<p>199 ₽</p><a href="/checkout/unavailable">Купить</a>'
        body+='</section>'
    elif path=='/admin':
        if not admin:raise ApiError(403,'Доступ только владельцу проекта.')
        title='Админ-панель'
        with backend.connect() as db:rows=db.execute('SELECT id FROM users ORDER BY id LIMIT 200').fetchall()
        body='<p>Галочка и Premium сохраняются в базе. Галочка видна в профилях и списках LuxBlox.</p>'
        for r in rows:
            u=user(backend,r['id'])
            body+='<section><h2>'+badge(u)+' <small>#'+str(u['id'])+'</small></h2>'+form('admin_flags','<input type="hidden" name="target" value="'+str(u['id'])+'">'+''.join('<label><input type="checkbox" name="'+k+'"'+(' checked' if u[f] else '')+'> '+name+'</label>' for k,f,name in [('verified','hasVerifiedBadge','Галочка'),('premium','isPremium','Premium')])+'<button>Сохранить</button>')+'</section>'
    elif path.startswith('/my/account/'):
        key=path.rsplit('/',1)[1];title={'security':'Безопасность','notifications':'Уведомления','billing':'Оплата','privacy':'Конфиденциальность'}.get(key,'Настройки')
        if key=='security':
            with backend.connect() as db:n=db.execute('SELECT COUNT(*) AS n FROM sessions WHERE user_id=? AND expires>?',(uid,int(time.time()))).fetchone()['n']
            body='<section><p>Активных сеансов: '+str(n)+'</p>'+form('logout_others','<button>Завершить остальные сеансы</button>')+'<p><a href="/my/account">Изменить пароль</a></p><p>Двухэтапная проверка пока недоступна.</p></section>'
        elif key=='billing':body='<section><p>Платёжные карты не привязаны. Платежи и списания отключены.</p><a href="/upgrades/robux">Наборы Robux</a> · <a href="/premium/membership">Premium</a></section>'
        else:
            p=preferences(backend,uid)
            body='<section>'+form('preferences',''.join('<label><input type="checkbox" name="'+k+'"'+(' checked' if p[k] else '')+'> '+name+'</label>' for k,name in [('friendRequestsEnabled','Принимать заявки в друзья'),('messagesEnabled','Принимать личные сообщения'),('friendNotifications','Уведомления о друзьях'),('messageNotifications','Уведомления о сообщениях'),('inventoryVisible','Открытый инвентарь')])+'<button>Сохранить</button>')+'</section>'
    elif re.fullmatch(r'/users/\d+/profile',path):
        target=int(path.split('/')[2]);u=user(backend,target);title='Профиль'
        body='<section><img class="avatar" src="/luxblox/avatar/'+str(target)+'.svg" alt="Персонаж"><h2>'+badge(u)+'</h2><p>@'+e(u['name'])+(' · Premium' if u['isPremium'] else '')+'</p></section>'
    else:title='Раздел LuxBlox';body='<p><a href="/more">Ещё</a></p>'
    notice='<p role="status" class="message">'+e(notice)+'</p>' if notice else ''
    css=STYLE+'''select{width:100%;padding:10px;margin:8px 0}input[type=checkbox]{width:auto}form{margin:10px 0}.tabs{display:flex;flex-wrap:wrap;gap:12px}.cover{width:100%;max-height:260px;object-fit:cover}.avatar{display:block;width:180px;margin:auto}.secondary{background:#69777e}.badge{background:#1687d9;color:#fff;border-radius:50%;padding:1px 5px}.play{display:block;background:#00a65a;color:white;text-align:center;padding:14px;text-decoration:none;border-radius:4px}'''
    return ('<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+' — LuxBlox</title><style>'+css+'</style><header>LuxBlox</header><main>'+nav+'<h1>'+e(title)+'</h1>'+notice+body+'</main></html>').encode()


def avatar_png(backend, uid):
    import struct,zlib
    c={k:bytes.fromhex(PALETTE[v][1:]) for k,v in avatar(backend,uid)['bodyColors'].items()}
    rows=[bytearray(bytes.fromhex('f2f4f5')*240) for _ in range(310)]
    for x,y,w,h,key in [(84,16,72,66,'headColorId'),(66,86,108,106,'torsoColorId'),(25,86,36,106,'leftArmColorId'),(179,86,36,106,'rightArmColorId'),(66,198,51,92,'leftLegColorId'),(123,198,51,92,'rightLegColorId')]:
        for yy in range(y,y+h):rows[yy][x*3:(x+w)*3]=c[key]*w
    for x,y,w,h in [(103,38,6,6),(131,38,6,6),(106,59,28,3)]:
        for yy in range(y,y+h):rows[yy][x*3:(x+w)*3]=b'\x33\x33\x33'*w
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',240,310,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\x00'+r for r in rows)))+chunk(b'IEND',b'')


def wear_assets(backend,uid,asset_ids):
    if not isinstance(asset_ids,list) or len(asset_ids)>1 or any(type(i)!=int or i not in {p['id'] for p in SHIRTS} for i in asset_ids):raise ApiError(400,'Можно надеть одну рубашку из каталога LuxBlox.')
    with backend.connect() as db:
        for i in asset_ids:
            if not db.execute('SELECT 1 FROM catalog_owned WHERE user_id=? AND item_id=?',(uid,i)).fetchone():raise ApiError(403,'Предмет отсутствует в инвентаре.')
        db.execute('DELETE FROM avatar_worn WHERE user_id=?',(uid,))
        for i in asset_ids:db.execute('INSERT INTO avatar_worn(user_id,item_id) VALUES(?,?)',(uid,i))
    if asset_ids:
        color=next(p['color'] for p in SHIRTS if p['id']==asset_ids[0])
        set_avatar(backend,uid,dict(avatar(backend,uid)['bodyColors'],torsoColorId=color))
