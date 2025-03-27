"""Install the ``entangler`` package for use in ARTIQ.

You can install this package locally (in development mode) using:
``$ pip install -e .``.
"""
import setuptools

if __name__ == "__main__":
    setuptools.setup(
        name="entangler",
        version="1.4.0",
        packages=setuptools.find_packages(),
        requirements=["artiq>=5", "dynaconf>=3", "mergedeep", "numpy"],
        url="https://github.com/drewrisinger/entangler-core",
        package_data={
            "": ["*.txt", "*.toml", "*.md", "*.json"],
        },
        extras_require={
            "gateware": [
                "jsonschema",
                "migen",
                "misoc",
            ]
        },
    )
