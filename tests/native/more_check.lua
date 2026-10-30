local function count(page,uid)
 game:GetService('Players').LocalPlayer.UserId=uid
 local groups=_result.GetItemsInPage(page,false)
 assert(type(groups)=='table')
 local admin,launch=0,0
 local flat=groups[1] and groups[1].itemType~=nil
 local lists=flat and {groups} or groups
 local total=0
 for _,group in ipairs(lists)do
  for _,item in ipairs(group)do
   total=total+1
   assert(item.itemType~=nil)
   if item.itemType==_result.ItemType.CreateGames then admin=admin+1;assert(item.context.url=='https://luxblox-api.onrender.com/admin')end
   if item.itemType==_result.ItemType.MyFeed then launch=launch+1;assert(item.context.url=='https://luxblox-api.onrender.com/games/start?placeid=1001')end
  end
 end
 assert(admin==(uid==2 and 1 or 0),'Incorrect admin tile count '..tostring(admin))
 assert(launch==1,'Missing or duplicate launch tile')
 assert(total>2,'Original More items were lost')
end
for _,nested in ipairs({false,true})do FLAG_NEST=nested;for _,page in ipairs({'More','CJVMore','SimplifiedMore'})do count(page,2);count(page,7)end end
print('Native More groups: owner, ordinary user and all page policies OK')
