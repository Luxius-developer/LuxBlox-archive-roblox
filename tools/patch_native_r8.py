"""Patch reviewed R7 native modules. Requires the local Luau-501 harness."""
import argparse,hashlib,json,re,struct,subprocess,zipfile
from pathlib import Path
from tools.patch_native_bundle import chunks,read_string,rbx_string,unpack_script,pack_script,DMP
from tools.luau_v1 import parse,serialize,add_string,add_constant,append_wrapper,convert
ORIGIN='https://luxblox-api.onrender.com'
PATTERN='^https://luxblox%-api%.onrender%.com/'
EXPECTED='94322a04179f5b3483f7129080fef9a545a52c030874ba843d73219902adb5da'


def compile_wrapper(compiler,source):
    p=Path('/tmp/luxblox-r8-wrapper.lua');p.write_text(source)
    return convert(parse(subprocess.check_output([compiler,'compile',str(p)])),True)


def patch_script(raw,index,name,compiler):
    c=parse(raw);changes=[]
    if index in (4166,4569,5086):
        for p in c['protos']:
            pname=c['strings'][p['name']-1].decode() if p['name'] else ''
            for k in p['constants']:
                if k[0]!=3:continue
                old=c['strings'][k[1]-1].decode();new=old
                if index==4166:
                    service=re.fullmatch(r'https://(api|chat|games|metrics|thumbnails)\.',old)
                    if service:new=ORIGIN+'/'+service[1]+'/'
                    if old=='https://www.':new=ORIGIN+'/'
                    if old in ('https://friends.%sv1/','https://presence.%sv1/'):new=ORIGIN+'/'+old.split('://')[1].split('.')[0]+'/v1/'
                elif index==4569:
                    if old in ('https://www','https://www.'):new=PATTERN
                    service=re.fullmatch(r'https://(api|apis|abtesting|catalog|economy|premiumfeatures|economycreatorstats)\.?',old)
                    if service:new=ORIGIN+'/'+service[1]+'/'
                else:
                    if old=='https://www.':new=PATTERN
                    if pname=='buildServiceUrl':
                        if old=='https://':new=ORIGIN+'/'
                        if old=='.':new='/'
                    if old=='https://assetgame.':new=ORIGIN+'/assetgame/'
                    if old=='https://accountsettings.':new=ORIGIN+'/accountsettings/'
                if old!=new:k[1]=add_string(c,new);changes.append([pname,old,new])
        if index==4166:
            p=c['protos'][c['main']]
            # Its original sub(13)/sub(12) parser assumes a www host. With
            # explicit service origins, start with an empty domain suffix.
            if (p['code'][100]&255)*203%256!=15 or p['code'][101]!=27:raise ValueError('Unexpected WebApi main')
            constant=add_constant(c,p,'');p['code'][100]=(5*227&255)|(20<<8)|(constant<<16);p['code'][101]=0
            changes.append(['main','fixed www suffix offsets','explicit service origins'])
    if index==3522:
        append_wrapper(c,compile_wrapper(compiler,(Path(__file__).parent/'native_more.lua').read_text()))
        changes.append(['MorePageSettings','native groups','explicit admin and game-launch tiles'])
    if index in (2952,4877):
        for p in c['protos']:
            for k in p['constants']:
                if k[0]!=3:continue
                old=c['strings'][k[1]-1].decode();new=old
                if index==4877:new=old.replace('https://games.roblox.com/',ORIGIN+'/games/')
                if index==2952:new=old.replace('http://www.roblox.com/asset/?id=',ORIGIN+'/asset/?id=')
                if old!=new:k[1]=add_string(c,new);changes.append(['native resource URL',old,new])
    if re.fullmatch(r'[a-z]{2}(?:-[a-z]+)?',name) and b'CommonUI.Features.Label.FMODCredits' in c['strings']:
        source='local t=...;t["CommonUI.Features.Label.CreateGames"]="Админ-панель";t["CommonUI.Features.Label.MyFeed"]="Запустить 3D-плейс";t["CommonUI.Features.Label.FMODCredits"]="Использует FMOD от Firelight Studios\\nСделано Vortix Studio";return t'
        append_wrapper(c,compile_wrapper(compiler,source));changes.append(['locale','labels and footer','FMOD credit retained; Vortix Studio line added'])
    new=serialize(c)
    if serialize(parse(new))!=new:raise ValueError('Bytecode roundtrip failed')
    return new,changes


def scripts(data):
    cs=list(chunks(data));counts={};names={}
    for kind,p,_ in cs:
        if kind==b'INST':
            cid=struct.unpack_from('<I',p)[0];_,j=read_string(p,4);counts[cid]=struct.unpack_from('<I',p,j+1)[0]
        if kind==b'PROP':
            cid=struct.unpack_from('<I',p)[0];prop,j=read_string(p,4);j+=1
            if prop==b'Name':
                names[cid]=[]
                for _ in range(counts[cid]):s,j=read_string(p,j);names[cid].append(s.decode())
    return cs,counts,names


def patch_model(data,compiler):
    cs,counts,names=scripts(data);out=data[:32];report=[]
    for kind,p,reserved in cs:
        if kind==b'PROP':
            cid=struct.unpack_from('<I',p)[0];prop,j=read_string(p,4);typ=p[j];j+=1
            if prop==b'Source' and typ==29:
                updated=p[:j]
                for i in range(counts[cid]):
                    blob,j=read_string(p,j);name=names[cid][i]
                    if blob and (i in (4166,4569,5086,3522,2952,4877) or re.fullmatch(r'[a-z]{2}(?:-[a-z]+)?',name)):
                        new,changes=patch_script(unpack_script(blob),i,name,compiler)
                        if changes:
                            blob=pack_script(new);assert unpack_script(blob)==new
                            report.append(dict(index=i,module=name,changes=changes,sha256=hashlib.sha256(new).hexdigest()))
                    updated+=rbx_string(blob)
                p=updated
        out+=struct.pack('<4sIII',kind,0,len(p),reserved)+p
    return out,report


def patch(decoded,compiler):
    root=Path(decoded);obb=root/'assets/main.1.com.roblox.client.obb';temp=obb.with_suffix('.r8.tmp')
    with zipfile.ZipFile(obb) as src,zipfile.ZipFile(temp,'w') as dst:
        data=src.read(DMP)
        if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Unreviewed R7 bundle')
        new,report=patch_model(data,compiler)
        for info in src.infolist():dst.writestr(info,new if info.filename==DMP else src.read(info))
    temp.replace(obb)
    backup=root/'assets/main.1.com.roblox.client.obb.bak'
    removed=backup.stat().st_size if backup.exists() else 0
    if backup.exists():backup.unlink()
    return {'modules':report,'unused_backup_bytes_removed':removed,'native_libraries_modified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('decoded');p.add_argument('--compiler',required=True);a=p.parse_args()
    print(json.dumps(patch(a.decoded,a.compiler),ensure_ascii=False,indent=2))
