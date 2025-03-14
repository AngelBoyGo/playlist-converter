from setuptools import setup, find_packages

setup(
    name="playlist-converter",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "selenium",
        "webdriver-manager",
        "beautifulsoup4",
        "requests",
        "aiohttp",
        "asyncio",
        "python-dotenv",
    ],
) 