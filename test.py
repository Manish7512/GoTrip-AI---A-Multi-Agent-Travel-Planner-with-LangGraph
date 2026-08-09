from tools.tavily_tool import tavily_search

# res = tavily_search("Best hotel in London")
# print(res)

from tools.flight_tool import search_flights
res = search_flights("Plan a 7 days Nepal trip from India")
print(res)