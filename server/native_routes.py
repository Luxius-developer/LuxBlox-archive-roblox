"""Additional endpoints requested by the embedded 2021 Http and LuaChat modules."""
import re
from urllib.parse import parse_qs
from server import features as f, chat
from server.errors import ApiError


def route(h,path,url,namespace):
    b=h.server.backend;q=parse_qs(url.query);method=h.command
    def reply(data):h.reply(200,data);return True
    def me():return b.current_user(h.cookie_value('.ROBLOSECURITY'))
    if namespace=='games' and path=='/v1/games/game-thumbnail' and method in ('GET','HEAD'):
        token=q.get('imageToken',[''])[0]
        if token not in ('1001','luxblox-1001'):raise ApiError(404,'Миниатюра не найдена.')
        from pathlib import Path
        h.reply(200,(Path(__file__).parent/'static/place-1001.png').read_bytes(),[('Content-Type','image/png')]);return True
    if namespace=='thumbnails' and path in ('/v1/users/avatar-headshot','/v1/users/avatar-bust') and method in ('GET','HEAD'):
        ids=[int(x) for x in ','.join(q.get('userIds',[])).split(',') if x.isdigit()][:100]
        return reply({'data':[{'targetId':uid,'state':'Completed','imageUrl':f.avatar_url(b,uid)} for uid in ids]})
    if namespace=='thumbnails' and path=='/v1/batch' and method=='POST':
        # The client sends a JSON array here, unlike most API requests.
        import json
        try:
            n=int(h.headers.get('Content-Length','0'))
            if not 0<n<=65536 or h.headers.get('Transfer-Encoding'):raise ValueError()
            requests=json.loads(h.rfile.read(n))
            if not isinstance(requests,list) or len(requests)>100:raise ValueError()
        except (ValueError,TypeError):raise ApiError(400,'Некорректный пакет миниатюр.') from None
        items=[]
        for request in requests:
            if not isinstance(request,dict):raise ApiError(400,'Некорректная миниатюра.')
            uid=request.get('targetId');typ=request.get('type')
            if type(uid)!=int:raise ApiError(400,'Некорректный targetId.')
            if typ in ('Avatar','AvatarHeadShot','AvatarBust'):
                image=f.avatar_url(b,uid)
            elif typ in ('GameIcon','PlaceIcon') and uid==1001:image=b.public_origin+'/static/place-1001.png'
            else:continue
            items.append({'requestId':request.get('requestId',''),'targetId':uid,'state':'Completed','imageUrl':image,'errorCode':0,'errorMessage':''})
        return reply({'data':items})
    if path in ('/avatar-thumbnail/json','/headshot-thumbnail/json') and method in ('GET','HEAD'):
        try:uid=int(q.get('userId',['0'])[0])
        except ValueError:raise ApiError(400,'Некорректный ID.') from None
        return reply({'Url':f.avatar_url(b,uid),'Final':True,'SubstitutionType':0})
    if path in ('/places/icons/json','/places/api-get-details','/PlaceItem/GameDetailsVotingPanelJson','/thumbnail/place-thumbnails') and method in ('GET','HEAD'):
        try:pid=int(q.get('placeId',q.get('assetId',['0']))[0])
        except ValueError:raise ApiError(400,'Некорректный плейс.') from None
        if pid!=1001:raise ApiError(404,'Плейс не найден.')
        if path=='/places/icons/json':return reply({'ImageId':1001,'Url':b.public_origin+'/static/place-1001.png','Final':True})
        if path=='/PlaceItem/GameDetailsVotingPanelJson':
            v=f.votes(b);return reply({'UpVotes':v['upVotes'],'DownVotes':v['downVotes'],'CanVote':True})
        if path=='/thumbnail/place-thumbnails':return reply([{'Url':b.public_origin+'/static/place-1001.png','Final':True}])
        return reply({'AssetId':1001,'UniverseId':1001,'Name':'LuxBlox Starter Obby','Description':'Старт, десять платформ и финиш.','Builder':'Vortix Studio','BuilderId':b.owner_user_id,'MaxPlayers':8,'IsPlayable':False})
    if namespace=='chat' and path=='/v2/multi-get-latest-messages' and method in ('GET','HEAD'):
        uid=me()['id'];out=[]
        ids=[int(i) for i in ','.join(q.get('conversationIds',[])).split(',') if i.isdigit()][:50]
        for cid in ids:
            messages=chat.conversation_messages(b,cid,uid,page_size=1)
            out.append({'conversationId':cid,'chatMessages':messages})
        return reply(out)
    if namespace=='chat' and path=='/v2/get-conversations' and method in ('GET','HEAD') and 'conversationIds' in q:
        uid=me()['id'];ids=[int(i) for i in ','.join(q['conversationIds']).split(',') if i.isdigit()][:50]
        return reply([chat.conversation(b,cid,uid) for cid in ids])
    if namespace=='chat' and path in ('/v2/mark-as-read','/v2/update-user-typing-status') and method=='POST':
        uid=me()['id']
        if not h.require_csrf():return True
        body=h.read_json();chat.conversation(b,body.get('conversationId'),uid)
        return reply({'resultType':'Success'})
    return False
