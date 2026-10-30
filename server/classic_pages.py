"""Compact WebView pages following the older site's spacing and sections."""
from html import escape


def premium(me,owner,form):
    body='''<section class="premium-hero"><h2><span class="premium-mark">P</span> Premium</h2><p>Больше возможностей в LuxBlox</p></section>
    <section><h2>Участие в Premium</h2><ul class="benefits"><li>Значок Premium рядом с профилем</li><li>Статус участника в аккаунте</li></ul><p class="muted">Ежемесячные Robux, скидки и торговля пока не предоставляются.</p></section>'''
    body+='<section><h2>Ваше участие</h2><p class="membership-state">'+('Premium активен' if me['isPremium'] else 'Premium не активирован')+'</p>'
    if owner:
        body+=form('premium','<button>Активировать бесплатно для себя</button>')
        body+='<h3>Подарить участие</h3>'+form('premium','<label>Username получателя<input name="username" required minlength="3" maxlength="20" autocomplete="off" placeholder="Например, Luxius"></label><button>Подарить Premium</button>')
    else:body+='<p>199 ₽</p><a class="play" href="/checkout/unavailable">Купить</a>'
    return body+'</section>'


def profile(backend,viewer,u,form):
    from server import features as f
    e=lambda s:escape(str(s),quote=True)
    uid=u['id'];friends=f.friends(backend,uid)
    body='<section class="profile-heading"><img class="profile-head" src="'+e(f.avatar_url(backend,uid))+'" alt="Аватар"><div><h2>'+e(u['displayName'])+'</h2><p>@'+e(u['name'])+'</p>'+('<p>Premium</p>' if u['isPremium'] else '')+'</div></section>'
    body+='<section><div class="profile-stats"><span><strong>'+str(len(friends))+'</strong> Друзья</span></div>'
    if viewer!=uid:
        mine={x['id'] for x in f.friends(backend,viewer)}
        if uid in mine:body+='<p>Вы друзья · <a href="/my/messages">Написать сообщение</a></p>'
        else:body+=form('friend_request','<input type="hidden" name="target" value="'+str(uid)+'"><button>Добавить в друзья</button>')
    body+='</section><section><h2>О пользователе</h2><p>Участник LuxBlox</p></section><section><h2>Друзья ('+str(len(friends))+')</h2><div class="people-grid">'
    for friend in friends[:12]:
        body+='<a class="person" href="/users/'+str(friend['id'])+'/profile"><img src="'+e(f.avatar_url(backend,friend['id']))+'" alt=""><span>'+e(friend['displayName'])+'</span></a>'
    body+='</div></section><section><h2>Инвентарь</h2><a href="/users/'+str(uid)+'/inventory">Посмотреть предметы →</a></section>'
    return body


CSS='''.profile-heading{display:flex;align-items:center;gap:20px}.profile-heading h2{margin:0}.profile-head{width:100px;height:100px;object-fit:contain;border-radius:50%;background:#e4e7ea}.profile-stats{display:flex;gap:30px}.profile-stats strong{display:block;font-size:24px}.people-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:16px}.person{text-align:center;text-decoration:none;overflow-wrap:anywhere}.person img{display:block;width:86px;height:86px;object-fit:contain;border-radius:50%;background:#e5e7ea;margin:auto}.person span{display:block;margin-top:8px}.friend-row{display:flex;align-items:center;gap:14px}.friend-row img{width:72px;height:72px;object-fit:contain;background:#e5e7ea;border-radius:50%}.friend-info{flex:1;min-width:0}.friend-actions{display:flex;gap:8px}.friend-actions form{flex:1}.friend-actions button{font-size:14px;padding:10px}.premium-hero{text-align:center;padding:28px 15px!important}.premium-hero h2{font-size:32px}.premium-mark{font-style:italic;font-weight:bold}.benefits{padding-left:22px;line-height:2}.membership-state{padding:12px;background:#e8f4ed;border-left:4px solid #00a65a}'''
