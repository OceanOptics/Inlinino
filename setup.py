import setuptools
import codecs
import os.path

with open("README.md", "r") as fh:
    long_description = fh.read()

with codecs.open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'inlinino', '__init__.py'), 'r') as fp:
    for line in fp.read().splitlines():
        if line.startswith('__version__'):
            delimiter = '"' if '"' in line else "'"
            __version__ = line.split(delimiter)[1]
            break
    else:
        raise RuntimeError("Unable to find version string.")

setuptools.setup(
    name="Inlinino",
    version=__version__,
    author="Nils Haentjens",
    author_email="nils.haentjens@maine.edu",
    description="A modular software data logger for oceanography",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/OceanOptics/Inlinino",
    packages=setuptools.find_packages(),
    install_requires=['pyserial>=3.4', 'numpy', 'scipy', 'PyQt5>=5.15', 'pyqtgraph>=0.12.1', 'pyACS', 'pySatlantic', 'pynmea2'],
    python_requires='==3.8.*',
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