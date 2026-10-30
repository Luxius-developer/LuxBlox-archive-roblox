"""Execute patched, extracted client modules in the Luau-501 test harness."""
import argparse,hashlib,io,json,struct,subprocess,tempfile,zipfile
from pathlib import Path
from tools.patch_native_bundle import DMP,read_string,unpack_script
from tools.patch_native_r8 import EXPECTED,scripts,patch_script
from tools.luau_v1 import parse,serialize,convert,instructions


def verify(apk,compiler):
    if hashlib.sha256(Path(apk).read_bytes()).hexdigest()!='6f1a52c60e8c99fb40f351327fc2b721470b59174d66c1d5d915b534c456f1dd':raise ValueError('Unreviewed R7 APK')
    with zipfile.ZipFile(apk) as a:
        with zipfile.ZipFile(io.BytesIO(a.read('assets/main.1.com.roblox.client.obb'))) as z:data=z.read(DMP)
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Wrong native bundle')
    cs,counts,names=scripts(data)
    wanted={3522:'more_check.lua',5086:'http_check.lua',4166:'chat_check.lua',4569:'network_check.lua',3473:'locale_check.lua'}
    root=Path(__file__).resolve().parents[1];results=[]
    with tempfile.TemporaryDirectory() as directory:
        for kind,p,_ in cs:
            if kind!=b'PROP':continue
            cid=struct.unpack_from('<I',p)[0];prop,j=read_string(p,4);typ=p[j];j+=1
            if prop!=b'Source' or typ!=29:continue
            for i in range(counts[cid]):
                blob,j=read_string(p,j)
                if i not in wanted:continue
                raw=unpack_script(blob)
                if serialize(parse(raw))!=raw:raise ValueError('Original roundtrip failed')
                new,changes=patch_script(raw,i,names[cid][i],compiler)
                normalized=convert(parse(new),False)
                # The added wrappers use basic instructions available in 0.477.
                for proto in normalized['protos']:list(instructions(proto['code'],False))
                path=Path(directory)/f'{i}.bin';path.write_bytes(serialize(normalized))
                out=subprocess.check_output([compiler,'run',str(path),str(root/'tests/native/stub.lua'),str(root/'tests/native'/wanted[i])],text=True)
                print(out.strip());results.append({'module':names[cid][i],'index':i,'changes':len(changes),'executed':True})
    if len(results)!=len(wanted):raise ValueError('Missing test module')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('apk');p.add_argument('--compiler',required=True);a=p.parse_args();verify(a.apk,a.compiler)
