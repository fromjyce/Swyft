from setuptools import setup, find_packages

setup(
    name="swyft",
    version="0.1.0",
    description="Intelligent P2P Network Analyzer & Optimizer",
    author="fromjyce",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "aiohttp>=3.8.0",
        "bencodepy>=0.9.5",
        "click>=8.1.0",
        "rich>=13.5.0",
        "loguru>=0.7.0",
        "pydantic>=2.0.0",
        "PyYAML>=6.0",
        "numpy>=1.24.0",
        "scikit-learn>=1.3.0",
        "xgboost>=1.7.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "redis>=5.0.0",
        "cryptography>=41.0.0",
        "prometheus-client>=0.17.0",
    ],
    entry_points={
        "console_scripts": [
            "swyft=cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.11",
    ],
)
