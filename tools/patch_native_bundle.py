#!/usr/bin/env python3
"""Patch reviewed URL/menu constants in the 2021 native DataModelPatch bundle.

Preserves Luau instruction/prototype bytes, native libraries and CA bundle.
Requires system liblz4/libxxhash and Python zstandard only while building APKs.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile
import zstandard
from tools.patch_client import endpoint_map

DMP='ExtraContent/models/DataModelPatch/DataModelPatch.rbxm'
AVATAR_SCENE='content/places/AvatarEditor.rbxl'


def varint(data,pos):
    value=0
    for shift in range(0,35,7):
        if pos>=len(data):raise ValueError('Truncated varint')
        b=data[pos];pos+=1;value|=(b&127)<<shift
        if b<128:return value,pos
    raise ValueError('Oversized varint')


def encode_varint(value):
    out=bytearray()
    while value>=128:out.append((value&127)|128);value>>=7
    out.append(value);return bytes(out)


def read_string(data,pos):
    if pos+4>len(data):raise ValueError('Truncated RBX string')
    n=struct.unpack_from('<I',data,pos)[0];end=pos+4+n
    if end>len(data):raise ValueError('RBX string length exceeds chunk')
    return data[pos+4:end],end


def rbx_string(data):return struct.pack('<I',len(data))+data


def lib(name):
    path=ctypes.util.find_library(name)
    if not path:raise RuntimeError('Missing build dependency: '+name)
    return ctypes.CDLL(path)


def xxhash(data):
    x=lib('xxhash');x.XXH32.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint];x.XXH32.restype=ctypes.c_uint
    return x.XXH32(data,len(data),42)


def unpack_script(blob):
    if len(blob)<12:raise ValueError('Truncated native script')
    key=bytes(((blob[i]^b'RSB1'[i])-i*41)&255 for i in range(4))
    raw=bytes(b^((key[i%4]+i*41)&255) for i,b in enumerate(blob))
    if struct.pack('<I',xxhash(raw))!=key:raise ValueError('Native script checksum mismatch')
    size=struct.unpack_from('<I',raw,4)[0]
    data=zstandard.ZstdDecompressor().decompress(raw[8:],max_output_size=size)
    if len(data)!=size or data[0]!=1:raise ValueError('Unexpected Luau script/version')
    return data


def pack_script(data):
    raw=b'RSB1'+struct.pack('<I',len(data))+zstandard.ZstdCompressor(level=3).compress(data)
    key=struct.pack('<I',xxhash(raw))
    return bytes(b^((key[i%4]+i*41)&255) for i,b in enumerate(raw))


def patch_constants(data,name,origin):
    count,pos=varint(data,1);out=data[:pos];changes=[]
    for _ in range(count):
        n,pos=varint(data,pos);value=data[pos:pos+n];pos+=n;new=value
        try:text=value.decode('utf-8')
        except UnicodeDecodeError:text=''
        m=re.fullmatch(r'https://([a-z.]+)\.%s(v[123])?',text)
        if m:new=(origin+'/'+m[1]+'/'+(m[2] or '')).encode()
        elif text=='https://%s.%s':new=(origin+'/%s/').encode()
        elif text.startswith(('https://blog.roblox.com','https://corp.roblox.com')):
            new=(origin+('/blog/' if 'blog.' in text else '/info/')).encode()
        if name=='UrlBase':
            new={b'://':('://'+origin.split('://')[1]+'/').encode(),b'.':b'',b'.*://':b'.*',b'http':b'https'}.get(value,new)
        if name=='MorePageSettings':
            new={b'develop/landing':b'admin',b'feeds/inapp':b'games/start?placeid=1001',b'icons/menu/create_large':b'icons/menu/settings_large'}.get(value,new)
        if new!=value:changes.append({'from':text,'to':new.decode()})
        out+=encode_varint(len(new))+new
    # No instructions, constants indices or prototype metadata are rewritten.
    tail=data[pos:];out+=tail
    return out,changes,hashlib.sha256(tail).hexdigest()


def chunks(data):
    lz=lib('lz4');lz.LZ4_decompress_safe.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    pos=32
    while pos<len(data):
        kind,compressed,size,reserved=struct.unpack_from('<4sIII',data,pos);pos+=16
        payload=data[pos:pos+(compressed or size)];pos+=compressed or size
        if compressed:
            buf=ctypes.create_string_buffer(size)
            if lz.LZ4_decompress_safe(payload,buf,compressed,size)!=size:raise ValueError('Invalid RBX chunk')
            payload=buf.raw
        yield kind,payload,reserved
    if pos!=len(data):raise ValueError('RBX trailing data')


def patch_model(data,origin,protected):
    pieces=list(chunks(data));counts={};names={};audit=[]
    for kind,payload,_ in pieces:
        if kind==b'INST':
            cid=struct.unpack_from('<I',payload)[0];_,pos=read_string(payload,4);counts[cid]=struct.unpack_from('<I',payload,pos+1)[0]
        if kind==b'PROP':
            cid=struct.unpack_from('<I',payload)[0];prop,pos=read_string(payload,4);typ=payload[pos];pos+=1
            if prop==b'Name':
                values=[]
                for _ in range(counts[cid]):value,pos=read_string(payload,pos);values.append(value.decode())
                names[cid]=values
    output=data[:32]
    for kind,payload,reserved in pieces:
        if kind==b'PROP':
            cid=struct.unpack_from('<I',payload)[0];prop,pos=read_string(payload,4);typ=payload[pos];pos+=1
            if prop==b'Source' and typ==(29 if protected else 1):
                updated=payload[:pos]
                for i in range(counts[cid]):
                    blob,pos=read_string(payload,pos);name=names[cid][i];new=blob;changes=[]
                    if blob and protected:
                        raw=unpack_script(blob);newraw,changes,tail_hash=patch_constants(raw,name,origin)
                        if changes:
                            new=pack_script(newraw)
                            if unpack_script(new)!=newraw:raise ValueError('Script roundtrip failed')
                            audit.append({'module':name,'changes':changes,'unchanged_code_tail_sha256':tail_hash})
                    elif blob:
                        text=blob.decode()
                        # The legacy avatar scene also constructs subdomains directly.
                        old=text
                        text=re.sub(r'"https://(inventory|avatar|www)\."\s*\.\.\s*domainUrl',lambda m:'"'+origin+'/'+m[1]+'/"',text)
                        text=re.sub(r'"http://www\.roblox\.com/', '"'+origin+'/',text)
                        if text!=old:new=text.encode();audit.append({'script':name,'urls_rewritten':True})
                    updated+=rbx_string(new)
                if pos!=len(payload):raise ValueError('Unexpected source property layout')
                payload=updated
        # Uncompressed RBX chunks are valid and let the original decoder read them.
        output+=struct.pack('<4sIII',kind,0,len(payload),reserved)+payload
    return output,audit


def patch(decoded,origin,expected_dmp):
    endpoint_map(origin);origin=origin.rstrip('/');root=Path(decoded);obb=root/'assets/main.1.com.roblox.client.obb'
    tmp=obb.with_suffix('.native.tmp');report=[]
    with zipfile.ZipFile(obb) as src,zipfile.ZipFile(tmp,'w') as dst:
        if hashlib.sha256(src.read(DMP)).hexdigest()!=expected_dmp:raise ValueError('Unreviewed native bundle hash')
        for info in src.infolist():
            data=src.read(info)
            if info.filename in (DMP,AVATAR_SCENE):
                before=hashlib.sha256(data).hexdigest();data,changes=patch_model(data,origin,info.filename==DMP)
                report.append({'entry':info.filename,'before':before,'after':hashlib.sha256(data).hexdigest(),'modules':changes})
            dst.writestr(info,data)
    tmp.replace(obb)
    for path in (root/'res').glob('values*/strings.xml'):
        text=path.read_text()
        for key,value in [('CommonUI_Features_Label_CreateGames','Админ-панель'),('CommonUI_Features_Label_MyFeed','Запустить 3D-плейс')]:
            text=re.sub(r'(<string name="'+key+r'">).*?(</string>)',lambda m:m[1]+value+m[2],text,flags=re.S)
        path.write_text(text)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('decoded');p.add_argument('--origin',required=True);p.add_argument('--expected-dmp',required=True);a=p.parse_args()
    print(json.dumps(patch(a.decoded,a.origin,a.expected_dmp),ensure_ascii=False,indent=2))
