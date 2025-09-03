"""API client for ActivityInfo REST API."""
from typing import Any, Dict, Optional
import requests


class ActivityInfoAPIError(Exception):
    """Custom exception for ActivityInfo API errors."""
    pass


class APIClient:
    """Centralized HTTP client for ActivityInfo API."""
    
    def __init__(self, token: str, base_url: str = "https://www.activityinfo.org"):
        """Initialize the API client.
        
        Args:
            token: API authentication token
            base_url: Base URL for the ActivityInfo API
        """
        self.token = token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
    
    def get(self, endpoint: str) -> Dict[str, Any]:
        """Make a GET request to the API.
        
        Args:
            endpoint: API endpoint (without base URL)
            
        Returns:
            JSON response as dictionary
            
        Raises:
            ActivityInfoAPIError: If the API request fails
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ActivityInfoAPIError(f"GET request failed for {endpoint}: {e}")
    
    def post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to the API.
        
        Args:
            endpoint: API endpoint (without base URL)
            data: JSON data to send in request body
            
        Returns:
            JSON response as dictionary
            
        Raises:
            ActivityInfoAPIError: If the API request fails
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise ActivityInfoAPIError(f"POST request failed for {endpoint}: {e}")