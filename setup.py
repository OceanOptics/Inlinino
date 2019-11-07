import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Inlinino",
    version="2.0.0",
    author="Nils Haentjens",
    author_email="nils.haentjens@maine.edu",
    description="A data logger designed for optical instruments mounted on research vessels continuously measuring the optical properties of the ocean",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/OceanOptics/Inlinino/tree/tb-app",
    packages=setuptools.find_packages(),
    install_requires=['pyserial', 'paho-mqtt', 'requests', 'pandas', 'pyACS'],
    license='GPLv3',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research"
    ]
)