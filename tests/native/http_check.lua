_result.GetGameSortsAsync2()
assert(#REQUESTS>0,'No native request captured')
assert(REQUESTS[1]=='https://luxblox-api.onrender.com/games/v1/games/sorts?model.gameSortsContext=GamesAllSorts',REQUESTS[1])
print('Native Http URL:',REQUESTS[1])
