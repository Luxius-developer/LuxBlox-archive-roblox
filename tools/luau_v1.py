"""Version-1 parser/serializer, based on the public Luau release-501 format.

The existing client uses an opcode multiplier of 227. AUX words are data.
This module never changes the engine's verification code or native libraries.
"""
import struct
from tools.patch_native_bundle import varint, encode_varint
AUX={7,8,12,15,16,20,27,28,29,30,31,32,53,55,58,66,71,72,74,75}


def parse(data):
    if data[0]!=1:raise ValueError('Expected Luau version 1')
    pos=1
    def vi():
        nonlocal pos
        n,pos=varint(data,pos);return n
    def take(n):
        nonlocal pos
        value=data[pos:pos+n]
        if len(value)!=n:raise ValueError('Truncated bytecode')
        pos+=n;return value
    def byte():return take(1)[0]
    def word():return struct.unpack('<I',take(4))[0]
    strings=[take(vi()) for _ in range(vi())];protos=[]
    for _ in range(vi()):
        header=list(take(4));code=[word() for _ in range(vi())];constants=[]
        for _ in range(vi()):
            kind=byte()
            if kind==0:value=None
            elif kind==1:value=byte()
            elif kind==2:value=take(8)
            elif kind==3:value=vi()
            elif kind==4:value=word()
            elif kind==5:value=[vi() for _ in range(vi())]
            elif kind==6:value=vi()
            else:raise ValueError('Unknown constant type')
            constants.append([kind,value])
        kids=[vi() for _ in range(vi())];name=vi();start=pos
        if byte():
            gap=byte();take(len(code)+(((len(code)-1)>>gap)+1)*4)
        if byte():
            for _ in range(vi()):vi();vi();vi();byte()
            for _ in range(vi()):vi()
        protos.append(dict(header=header,code=code,constants=constants,kids=kids,name=name,debug=data[start:pos]))
    main=vi()
    if pos!=len(data):raise ValueError('Trailing bytecode')
    return dict(strings=strings,protos=protos,main=main)


def serialize(c):
    vi=encode_varint;out=bytearray(b'\1'+vi(len(c['strings'])))
    for s in c['strings']:out+=vi(len(s))+s
    out+=vi(len(c['protos']))
    for p in c['protos']:
        out+=bytes(p['header'])+vi(len(p['code']))+b''.join(struct.pack('<I',w) for w in p['code'])+vi(len(p['constants']))
        for kind,value in p['constants']:
            out.append(kind)
            if kind==1:out.append(value)
            elif kind==2:out+=value
            elif kind in (3,6):out+=vi(value)
            elif kind==4:out+=struct.pack('<I',value)
            elif kind==5:out+=vi(len(value))+b''.join(vi(k) for k in value)
        out+=vi(len(p['kids']))+b''.join(vi(k) for k in p['kids'])+vi(p['name'])+p['debug']
    return bytes(out+vi(c['main']))


def add_string(c,s):
    if isinstance(s,str):s=s.encode()
    try:return c['strings'].index(s)+1
    except ValueError:c['strings'].append(s);return len(c['strings'])


def add_constant(c,p,s):
    k=[3,add_string(c,s)]
    try:return p['constants'].index(k)
    except ValueError:p['constants'].append(k);return len(p['constants'])-1


def instructions(code,encoded=True):
    i=0
    while i<len(code):
        op=(code[i]&255)*(203 if encoded else 1)%256
        if op>75:raise ValueError('Unknown version-1 opcode')
        yield i,op
        i+=2 if op in AUX else 1
    if i!=len(code):raise ValueError('Truncated AUX')


def convert(c,encode):
    for p in c['protos']:
        for i,op in instructions(p['code'],not encode):p['code'][i]=(p['code'][i]&~255)|((op*227 if encode else op)&255)
    return c


def append_wrapper(c,w):
    p=c['protos'][c['main']];word=p['code'][-1]
    if (word&255)*203%256!=22 or (word>>16&255)!=2:raise ValueError('Expected one module result')
    if c['main']!=len(c['protos'])-1:raise ValueError('Expected main proto last')
    # The v1 loader resolves child prototypes immediately: children must be
    # serialized before their parent, including this newly injected wrapper.
    c['protos'].pop()
    result=word>>8&255;so=len(c['strings']);po=len(c['protos']);c['strings']+=w['strings']
    for q in w['protos']:
        for k in q['constants']:
            if k[0]==3 and k[1]:k[1]+=so
            elif k[0]==6:k[1]+=po
        q['kids']=[k+po for k in q['kids']]
        if q['name']:q['name']+=so
        if q['debug']!=b'\0\0':raise ValueError('Compile wrapper with debug level zero')
        c['protos'].append(q)
    entry=po+w['main']
    if c['protos'][entry]['header'][2]:raise ValueError('Wrapper has external captures')
    child=len(p['kids']);p['kids'].append(entry);r=p['header'][0]
    if r+2>254:raise ValueError('Insufficient scratch registers')
    def ins(op,a,b=0,d=0):return (op*227&255)|(a<<8)|(b<<16)|(d<<24)
    p['code'][-1:]=[ins(19,r,child&255,child>>8),ins(6,r+1,result),ins(21,r,2,2),ins(22,r,2)]
    p['header'][0]=r+2;p['debug']=b'\0\0'
    c['protos'].append(p);c['main']=len(c['protos'])-1
    return c
