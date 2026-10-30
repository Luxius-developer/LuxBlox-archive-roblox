-- Minimal Roblox service doubles for executing real, extracted Luau modules.
local function node(name)
 local t={_name=name}
 return setmetatable(t,{__index=function(self,k)
  local n=node(name..'.'..tostring(k));rawset(self,k,n);return n
 end,__call=function(self,...) return 'https://luxblox-api.onrender.com/'..name end})
end
local core=node('CoreGui')
local players={LocalPlayer={UserId=2}}
local provider={BaseUrl='https://luxblox-api.onrender.com/'}
REQUESTS={}
local http={JSONDecode=function(self,s)return {} end,JSONEncode=function()return '{}'end,UrlEncode=function(self,s)return s end}
game={GetService=function(self,key)
 if key=='ContentProvider' then return provider end
 if key=='CoreGui' then return core end
 if key=='Players' then return players end
 if key=='HttpService' then return http end
 return node(key)
end,DefineFastFlag=function(self,key,value)return value end,
HttpGetAsync=function(self,url)table.insert(REQUESTS,url);return '{}'end,
HttpPostAsync=function(self,url)table.insert(REQUESTS,url);return '{}'end}
script=node('script')
Enum=node('Enum')
settings=function()return {GetFFlag=function(self,key)return key=='LuaAppHttpsWebViews'end}end
local pages=setmetatable({},{__index=function(self,k)return k end})
local cryo={Dictionary={join=function(...)
 local t={};for _,src in ipairs({...})do for k,v in pairs(src)do t[k]=v end end;return t
end},List={filter=function(list,predicate)
 local result={};for i,v in ipairs(list)do if predicate(v,i)then table.insert(result,v)end end;return result
end,map=function(list,fn)local r={};for i,v in ipairs(list)do r[i]=fn(v,i)end;return r end,
findWhere=function(list,fn)for i,v in ipairs(list)do if fn(v,i)then return i end end end}}
require=function(mod)
 local name=mod._name or ''
 if string.match(name,'%.AppPage$')then return pages end
 if string.match(name,'%.Cryo$')then return cryo end
 if string.match(name,'%.FormFactor$')then return {WIDE='WIDE',COMPACT='COMPACT'}end
 if string.match(name,'%.Url$')then return {BASE_URL=provider.BaseUrl,BLOG_URL=provider.BaseUrl..'blog/',CORP_URL=provider.BaseUrl..'info/'}end
 if string.find(name,'GetFFlag') or string.find(name,'Flags%.')or string.match(name,'isNewFriendsEndpointsEnabled$')then return function()return FLAG_NEST==true and string.find(name,'NestLists')~=nil end end
 if string.match(name,'%.Utility$')then return {DebugLog=function()end}end
 if string.match(name,'%.Config$')then return {General={HttpDelay=0},PageSize=20}end
 if string.match(name,'%.HttpDebug$')then return {AddRequest=function()end,FinishRequest=function()end}end
 if string.match(name,'%.Constants$')then return {}end
 local result=node(name)
 result.new=function()return node(name..'.instance')end
 return result
end
