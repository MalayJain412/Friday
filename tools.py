import logging
from livekit.agents import function_tool,RunContext
import requests
from langchain_community.tools import DuckDuckGoSearchRun

@function_tool()
async def get_weather(city: str) -> str:
    """Get the current weather for a given city"""
    try:
        response = requests.get(f"https://wttr.in/{city}?format=3")
        if response.status_code == 200:
            logging.info(f"Weather for {city}: {response.text.strip()}")
            return response.text.strip()
        else:
            logging.error(f"Failed to get weather for {city}: {response.status_code}")
            return f"Failed to get weather for {city}: {response.status_code}"
    except Exception as e:
        logging.error(f"Error getting weather for {city}: {e}")
        return f"Error getting weather for {city}: {e}"
    
@function_tool()
async def search_web(query: str) -> str:
    """Search the web for information about a given query using DuckDuckGo Search"""
    try:
        results = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Search results for '{query}': {results}")
        return results
    except Exception as e:
        logging.error(f"Error searching the web for '{query}': {e}")
        return f"An error occurred while searching the web for '{query}'."