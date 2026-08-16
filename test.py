from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from backend import run_travel_agent

# res = tavily_search("Best hotel in London")
# print(res)

# from tools.flight_tool import search_flights
# res = search_flights("Plan a 7 days Nepal trip from India")
# print(res)
# res = run_travel_agent()
# print(res)

user_input = input("Enter travel request: ")

response = run_travel_agent(
    user_input= user_input,
    thread_id= "test_user"
)

print("\nFINAL RESPONSE:\n")
print(response["final_answer"])