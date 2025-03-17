const API_BASE_URL = 'http://localhost:8080';

export async function convertPlaylist(request: ConversionRequest): Promise<ConversionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/convert`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error('Conversion failed');
  }

  return response.json();
}

export async function searchAlternative(request: SearchRequest): Promise<Alternative[]> {
  const response = await fetch(`${API_BASE_URL}/api/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error('Search failed');
  }

  return response.json();
}