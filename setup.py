import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Inlinino",
    version="2.0.2",
    author="Nils Haentjens",
    author_email="nils.haentjens@maine.edu",
    description="A modular software data logger for oceanography",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/OceanOptics/Inlinino",
    packages=setuptools.find_packages(),
    install_requires=['pyserial>=3.4', 'numpy', 'pyqt ', 'pyqtgraph==0.10', 'pyACS'],
    python_requires='>=3.7',
    license='GPLv3',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "Environment :: X11 Applications :: Qt"
    ]
)