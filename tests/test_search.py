import pytest
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    return TestClient(app)

@patch("api.search.get_search_client")
def test_search_endpoint(mock_get_search_client, client):
    mock_os = MagicMock()
    mock_get_search_client.return_value = mock_os
    
    mock_os.search.return_value = {
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "uscode_sections",
                    "_source": {
                        "identifier": "t16/s1",
                        "heading": "National Park Service",
                        "num": "1",
                        "release_id": 1
                    },
                    "highlight": {
                        "heading": ["<em>National</em> Park Service"]
                    }
                }
            ]
        }
    }
    
    response = client.get("/api/v1/search?q=National")
    assert response.status_code == 200
    
    data = response.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    
    result = data["results"][0]
    assert result["identifier"] == "t16/s1"
    assert result["heading"] == "National Park Service"
    assert result["num"] == "1"
    assert result["type"] == "section"
    
    assert len(result["snippets"]) == 1
    assert result["snippets"][0]["field"] == "heading"
    assert result["snippets"][0]["text"] == "<em>National</em> Park Service"
