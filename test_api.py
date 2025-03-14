import requests
import json
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_api.log')
    ]
)
logger = logging.getLogger(__name__)

SERVER_URL = "http://localhost:8080"

def test_health_endpoint():
    """Test the health endpoint to ensure the API is running."""
    logger.info("Testing health endpoint")
    
    try:
        response = requests.get(f"{SERVER_URL}/api/health")
        logger.info(f"Health response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Health response data: {data}")
            return True
        else:
            logger.error(f"Health check failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error connecting to API: {str(e)}")
        return False

def test_convert_endpoint():
    """Test the convert endpoint with a sample Apple Music playlist."""
    logger.info("Testing convert endpoint with Apple Music playlist")
    
    test_url = "https://music.apple.com/us/playlist/levitated/pl.u-vxy6696sz1VKqBX"
    
    payload = {
        "url": test_url,
        "target_platform": "SoundCloud"
    }
    
    try:
        logger.info(f"Sending conversion request: {payload}")
        response = requests.post(
            f"{SERVER_URL}/api/convert", 
            json=payload, 
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"Conversion response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response data summary: {len(data.get('results', [])) if data else 'No data'} results")
            logger.debug(f"Full response data: {json.dumps(data, indent=2)}")
            return True
        else:
            logger.error(f"Conversion failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error during conversion request: {str(e)}")
        return False

def main():
    """Run the API tests."""
    logger.info("Starting API tests")
    
    # Test health endpoint
    if not test_health_endpoint():
        logger.error("Health endpoint test failed. Aborting further tests.")
        return
    
    logger.info("Health endpoint test passed. Proceeding with conversion test.")
    
    # Test convert endpoint
    test_convert_endpoint()
    
    logger.info("API tests completed")

if __name__ == "__main__":
    main() 