-- Augment the original native tile list. No web navigation bar is added.
local m=...
local old=m.GetItemsInPage
local appPage=require(game:GetService("CoreGui").RobloxGui.Modules.LuaApp.AppPage)
local function tile(kind,key,path)
    local item={}
    for k,v in pairs(m.ItemInfo[m.ItemType.Help]) do item[k]=v end
    item.itemType=kind;item.textKey=key;item.badgeComponent=nil;item.badgeCount=0
    item.context={page=appPage.GenericWebPage,titleKey=key,url="https://luxblox-api.onrender.com/"..path}
    item.urlGenerator=nil
    return item
end
m.GetItemsInPage=function(page,...)
    local source=old(page,...)
    if page~=appPage.More and page~=appPage.CJVMore and page~=appPage.SimplifiedMore then return source end
    local function filter(list)
        local result={}
        for _,item in ipairs(list) do
            if item.itemType~=m.ItemType.CreateGames and item.itemType~=m.ItemType.MyFeed then table.insert(result,item) end
        end
        return result
    end
    local flat=source[1] and source[1].itemType~=nil
    local groups={}
    if flat then groups=filter(source)
    else for i,group in ipairs(source) do groups[i]=filter(group) end end
    local userId=game:GetService("Players").LocalPlayer.UserId
    local extras={}
    if userId==2 or userId==3 then table.insert(extras,tile(m.ItemType.CreateGames,"CommonUI.Features.Label.CreateGames","admin")) end
    table.insert(extras,tile(m.ItemType.MyFeed,"CommonUI.Features.Label.MyFeed","games/start?placeid=1001"))
    if flat then
        local position=#groups+1
        for i,item in ipairs(groups) do if item.itemType==m.ItemType.LogOut then position=i;break end end
        for i,item in ipairs(extras) do table.insert(groups,position+i-1,item) end
    else table.insert(groups,math.max(1,#groups),extras) end
    return groups
end
return m
