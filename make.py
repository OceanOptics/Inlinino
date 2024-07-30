import os
import platform

import PyInstaller.__main__
import pyqtgraph
try:
    import hypernav
except ImportError:
    hypernav = None


root = os.path.join('.', 'bundle')
data_sep = ':'
icon_ext = 'ico'

# Set parameters specific to platform
if platform.system() not in ['Windows', 'Darwin', 'Linux']:
    raise ValueError(f"Platform {platform.system()} not supported.")
os_specific_args = []
if platform.system() == 'Windows':
    data_sep = ';'
    # Windows 7 specific
    # os_specific_args = ('--add-data=%s%s%s' % (os.path.join(PATH_TO_SITE_PACKAGES, 'kaleido', 'executable', '*'),
    #                     OS_OPERATOR, os.path.join('kaleido', 'executable')),)
elif platform.system() == 'Darwin':
    icon_ext = 'icns'
    os_specific_args = [
        # '--target-arch=universal2',  # Fails on GitHub but bundle works on both architecture
        # Required for code signing
        '--osx-bundle-identifier=com.umaine.sms.inlinino'
        # f'--codesign-identity={os.getenv("CODESIGN_HASH")}',
        # f'--osx-entitlements-file={os.path.join("Bundled", "entitlements.plist")}',
    ]

# Get version number (without importing file)
version = None
with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'inlinino', '__init__.py'), 'r') as f:
    for l in f:
        if l.startswith('__version__'):
            version = l.split('=')[1].strip(" \n'")
            break

# Include all data files
add_data = []
ls = [
    ('README.md', '.'),
    ('LICENSE', '.'),
    (os.path.join('inlinino', 'inlinino_cfg.json'), '.'),
    (os.path.join('inlinino', 'resources'), 'resources'),
    (os.path.join('inlinino', 'cfg', '*'), 'cfg'),
    (os.path.join(os.path.dirname(pyqtgraph.__file__), 'icons', '*.png'), os.path.join('pyqtgraph', 'icons')),
    (os.path.join(os.path.dirname(pyqtgraph.__file__), 'icons', '*.svg'), os.path.join('pyqtgraph', 'icons')),
]
if hypernav is not None:
    ls.extend([
        (os.path.join(os.path.dirname(hypernav.__file__), 'bin', '*.exe'), os.path.join('hypernav', 'bin')),
        (os.path.join(os.path.dirname(hypernav.__file__), 'calibrate', 'templates', '*.txt'),
         os.path.join('hypernav', 'calibrate', 'templates'))
    ])
for item, dest in ls:
    add_data.append(f'--add-data={os.path.abspath(item)}{data_sep}{dest}')
    # Require absolute path for GitHub workflow as data can be on different drive and relpath won't work.

# Include hidden imports
hidden_imports = []
for i in [
    'pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5',
    'pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5',
    'pyqtgraph.imageview.ImageViewTemplate_pyqt5',
]:
    hidden_imports.append(f'--hidden-import={i}')

# Bundle application
PyInstaller.__main__.run([
    f'--name=Inlinino-v{version}-{platform.system()}',
    f"--icon={os.path.relpath(os.path.join('inlinino', 'resources', f'inlinino.{icon_ext}'), root)}",
    f'--distpath={os.path.join(root, "dist")}',
    f'--workpath={os.path.join(root, "build")}',
    f'--specpath={root}',
    '--windowed',
    '--noconfirm',
    # '--log-level=DEBUG',
    # '--clean',
    # '--debug=imports',
    *add_data,
    *hidden_imports,
    *os_specific_args,
    os.path.join('inlinino', '__main__.py')
])
