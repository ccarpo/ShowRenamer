from setuptools import setup, find_packages

setup(
    name="showrenamer",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "fuzzywuzzy>=0.18.0",
        "python-Levenshtein>=0.23.0",
        "watchdog>=3.0.0",
    ],
)
