from setuptools import setup, find_packages

setup(
    name="food_ordering",
    version="0.0.1",
    description="Food ordering and nutrition chatbot app for Frappe",
    author="Aditya",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe"],
)

