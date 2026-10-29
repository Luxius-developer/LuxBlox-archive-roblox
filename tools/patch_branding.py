#!/usr/bin/env python3
"""Apply reviewed LuxBlox visual resources and legacy WebView URL routing."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile
from PIL import Image,ImageOps


def png(image,size):
    canvas=Image.new('RGBA',size,'white')
    fitted=ImageOps.contain(image,size,Image.Resampling.LANCZOS)
    canvas.alpha_composite(fitted,((size[0]-fitted.width)//2,(size[1]-fitted.height)//2))
    stream=io.BytesIO();canvas.save(stream,format='PNG',optimize=True)
    return stream.getvalue()


def patch(root,icon_path,wordmark_path):
    root=Path(root);icon=Image.open(icon_path).convert('RGBA');wordmark=Image.open(wordmark_path).convert('RGBA')
    changed=[]
    names={'ic_launcher.png','ic_launcher_round.png','ic_launcher_foreground.png','ic_launcher_background.png','ic_launcher_transparent.png','game_icon.png','roblox_logo.png','about_icon_grey.png'}
    for p in (root/'res').glob('*/*.png'):
        if p.name not in names:continue
        size=Image.open(p).size
        p.write_bytes(png(wordmark if p.name=='roblox_logo.png' else icon,size));changed.append(str(p.relative_to(root)))
    for n in ('ic_launcher.xml','ic_launcher_round.xml'):
        p=root/'res/mipmap-anydpi-v26'/n
        if p.exists():
            p.write_text('<?xml version="1.0" encoding="utf-8"?><adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android"><background android:drawable="@mipmap/ic_launcher_background"/><foreground android:drawable="@mipmap/ic_launcher_foreground"/></adaptive-icon>');changed.append(str(p.relative_to(root)))
    for name in ('ic_launcher_foreground.xml', '$ic_launcher_foreground__0.xml'):
        p=root/'res/drawable-v24'/name
        if p.exists():
            p.write_text('<?xml version="1.0" encoding="utf-8"?><bitmap xmlns:android="http://schemas.android.com/apk/res/android" android:src="@mipmap/ic_launcher_foreground" android:gravity="center"/>')
            changed.append(str(p.relative_to(root)))
    for p in (root/'res').glob('values*/strings.xml'):
        text=p.read_text()
        # Change visible text only. Keep resource names, class names, JNI and licenses.
        def visible(m):
            value=m[2]
            if re.search(r'copyright|license|licence|attribution',m[1],re.I):return m[0]
            value=re.sub(r'\b(?:Roblox|Korone|Pekora)\b','LuxBlox',value,flags=re.I)
            return m[1]+value+m[3]
        new=re.sub(r'(<string\b[^>]*>)(.*?)(</string>)',visible,text,flags=re.S)
        new=new.replace('Please email info@LuxBlox.zip.','Please open LuxBlox Help.')
        if new!=text:p.write_text(new);changed.append(str(p.relative_to(root)))
    # Route navigations and external-browser dispatches for legacy brand domains.
    helper=root/'smali/com/luxius/luxblox/LegacyLinks.smali';helper.parent.mkdir(parents=True,exist_ok=True)
    helper.write_text((Path(__file__).parent/'LegacyLinks.smali').read_text())
    calls=0
    for p in root.glob('smali*/com/roblox/**/*.smali'):
        text=p.read_text()
        def rewrite(m):
            nonlocal calls
            registers=m[2]
            reg=registers.split(' .. ')[-1].strip() if ' .. ' in registers else registers.split(',')[-1].strip()
            if not re.fullmatch('[vp][0-9]+',reg):raise ValueError('Unexpected URL register')
            calls+=1
            return (m[1]+f'invoke-static/range {{{reg} .. {reg}}}, Lcom/luxius/luxblox/LegacyLinks;->localize(Ljava/lang/String;)Ljava/lang/String;\n'+m[1]+f'move-result-object {reg}\n'+m[0])
        pattern=r'(^[ \t]*)invoke-virtual(?:/range)? \{([^}]+)\}, Landroid/webkit/WebView;->loadUrl\(Ljava/lang/String;\)V'
        new=re.sub(pattern,rewrite,text,flags=re.M)
        if p.name=='x.smali' and p.parent.name=='client':
            new=re.sub(r'(^[ \t]*)invoke-static(?:/range)? \{([^}]+)\}, Landroid/net/Uri;->parse\(Ljava/lang/String;\)Landroid/net/Uri;',rewrite,new,flags=re.M)
        new=new.replace('https://en.help.pekora.zip/hc/articles/360000015683','https://luxblox-api.onrender.com/help').replace('https://en.help.pekora.zip/hc/articles/360001290106','https://luxblox-api.onrender.com/help')
        if new!=text:p.write_text(new);changed.append(str(p.relative_to(root)))
    obb=root/'assets/main.1.com.roblox.client.obb';tmp=obb.with_suffix('.brand.tmp');obb_changes=[]
    with zipfile.ZipFile(obb) as src,zipfile.ZipFile(tmp,'w') as dst:
        for info in src.infolist():
            data=src.read(info)
            if info.filename in {'content/textures/loading/robloxlogo.png','ExtraContent/textures/ui/LuaApp/graphic/Auth/logo_white_1x.png'}:
                size=Image.open(io.BytesIO(data)).size;data=png(wordmark,size);obb_changes.append(info.filename)
            dst.writestr(info,data)
    tmp.replace(obb)
    if calls<1:raise ValueError('No reviewed WebView navigation points found')
    return {'resource_files':changed,'web_url_calls':calls,'obb_brand_assets':obb_changes,'native_libraries_modified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('decoded');p.add_argument('--icon',required=True);p.add_argument('--wordmark',required=True);a=p.parse_args()
    print(json.dumps(patch(a.decoded,a.icon,a.wordmark),indent=2))
