#!/usr/bin/env python3
"""Route reviewed plaintext Lua URL builders to one HTTPS origin."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from tools.patch_client import endpoint_map

URL_MODULES = {
    'ExtraContent/LuaPackages/AppTempCommon/LuaApp/Http/Url.lua',
    'ExtraContent/scripts/CoreScripts/Modules/InGameMenu/Network/Url.lua',
}
URL_BASE = 'ExtraContent/LuaPackages/Packages/_Index/roblox_url-builder/url-builder/UrlBase.lua'
SITE_MODULES = {
    f'ExtraContent/LuaPackages/Packages/_Index/roblox_networking-{name}/networking-{name}/buildApiSiteUrl.lua'
    for name in ('friends', 'presence', 'users')
}


def rewrite(name, source, origin):
    endpoint_map(origin)  # Validate before inserting into Lua literals.
    base = origin.rstrip('/')
    if name in URL_MODULES:
        start = source.index('local function parseBaseUrlInformation()')
        end = source.index('\nend', start) + len('\nend')
        source = source[:start] + ('local function parseBaseUrlInformation()\n'
            f'\treturn "{base}/", "www", "{base.split("://", 1)[1]}/"\nend') + source[end:]
        pattern = r'string\.format\("https://([a-z.]+)\.%s([^"\n]*)", _baseDomain\)'
        source, count = re.subn(pattern, lambda m: f'"{base}/{m[1]}/{m[2]}"', source)
        if count < 20:
            raise ValueError('Unexpected URL table layout')
        source = source.replace('https://blog.roblox.com/', base + '/blog/').replace('https://corp.roblox.com/', base + '/corp/')
    elif name == URL_BASE:
        start = source.index('\tlocal urlbase = proto')
        end = source.index('\n\treturn urlbase', start) + len('\n\treturn urlbase')
        source = source[:start] + (f'\tlocal urlbase = "{base}"\n'
            '\tif #name > 0 then urlbase = urlbase .. "/" .. name end\n'
            '\tif version ~= nil and #tostring(version) > 0 then\n'
            '\t\turlbase = urlbase .. "/v" .. tostring(version)\n\tend\n'
            '\tif path ~= nil and #path > 0 then urlbase = urlbase .. "/" .. path end\n'
            '\treturn urlbase') + source[end:]
        source = source.replace('"https://blog.roblox.com"', f'"{base}/blog"')
        source = source.replace('isQQ and "https://roblox.qq.com" or "https://corp.roblox.com"', f'"{base}/corp"')
        source = source.replace('"https://ro.blox.com"', f'"{base}/telemetry"')
    elif name in SITE_MODULES:
        old = 'return string.format("https://%s.%s", siteName, baseDomain)'
        if source.count(old) != 1:
            raise ValueError('Unexpected site builder layout')
        source = source.replace(old, f'return "{base}/" .. siteName .. "/"')
    else:
        raise ValueError('Unreviewed module')
    return source


def patch_obb(path, origin):
    path = Path(path)
    temp = path.with_suffix('.route-patch.tmp')
    targets = URL_MODULES | SITE_MODULES | {URL_BASE}
    changes = []
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(temp, 'w') as dst:
        if not targets.issubset(src.namelist()):
            raise ValueError('Missing reviewed Lua modules')
        for info in src.infolist():
            data = src.read(info)
            if info.filename in targets:
                old = data
                data = rewrite(info.filename, data.decode('utf-8'), origin).encode('utf-8')
                changes.append({'path': info.filename, 'before': hashlib.sha256(old).hexdigest(),
                                'after': hashlib.sha256(data).hexdigest()})
            dst.writestr(info, data)
    temp.replace(path)
    return changes


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('obb', type=Path)
    parser.add_argument('--api-base', required=True)
    args = parser.parse_args()
    print(json.dumps(patch_obb(args.obb, args.api_base), indent=2))
