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
    local groups={}
    for i,group in ipairs(source) do
        local list={}
        for _,item in ipairs(group) do
            if item.itemType~=m.ItemType.CreateGames and item.itemType~=m.ItemType.MyFeed then table.insert(list,item) end
        end
        groups[i]=list
    end
    local userId=game:GetService("Players").LocalPlayer.UserId
    local extras={}
    if userId==2 or userId==3 then table.insert(extras,tile(m.ItemType.CreateGames,"CommonUI.Features.Label.CreateGames","admin")) end
    table.insert(extras,tile(m.ItemType.MyFeed,"CommonUI.Features.Label.MyFeed","games/start?placeid=1001"))
    table.insert(groups,math.max(1,#groups),extras)
    return groups
end
return m
