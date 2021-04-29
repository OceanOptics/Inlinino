import PyInstaller.__main__
from inlinino import __version__
import os
import platform

if platform.system() == 'Windows':
    # Windows
    OS_OPERATOR = ';'
    ICON_EXT = 'ico'
    DIST_PATH = 'dist_windows'
    PATH_TO_PYQTGRAPH_ICONS = r'C:\Users\nils\AppData\Local\Programs\Python\Python38\Lib\site-packages\pyqtgraph\icons'
elif platform.system() == 'Darwin':
    # macOS
    OS_OPERATOR = ':'
    ICON_EXT = 'icns'
    DIST_PATH = 'dist_darwin'
    PATH_TO_PYQTGRAPH_ICONS = '/usr/local/Caskroom/miniconda/base/envs/Inlinino/lib/python3.8/site-packages/pyqtgraph/icons'
    # TODO add version number in plist of spec file (CFBundleVersion)
    # https://pyinstaller.readthedocs.io/en/stable/spec-files.html?highlight=info_plist
    # https://developer.apple.com/library/archive/documentation/General/Reference/InfoPlistKeyReference/Articles/CoreFoundationKeys.html#//apple_ref/doc/uid/20001431-102364
else:
    # Linux
    OS_OPERATOR = ':'
    ICON_EXT = 'ico'
    DIST_PATH = 'dist_linux'

PyInstaller.__main__.run([
    '--name=Inlinino-v%s' % __version__,
    '--add-data=%s%s.' % (os.path.join('README.md'), OS_OPERATOR),
    '--add-data=%s%s.' % (os.path.join('LICENSE'), OS_OPERATOR),
    '--add-data=%s%s.' % (os.path.join('inlinino', 'inlinino_cfg.json'), OS_OPERATOR),
    '--add-data=%s%sresources' % (os.path.join('inlinino', 'resources'), OS_OPERATOR),
    '--add-data=%s%scfg' % (os.path.join('inlinino', 'cfg', '*'), OS_OPERATOR),
    '--icon=%s' % os.path.join('inlinino', 'resources', 'inlinino.%s' % ICON_EXT),
    '--osx-bundle-identifier=com.umaine.sms.inlinino',
    '--distpath=%s' % DIST_PATH,
    # pyqtgraph hidden imports
    '--hidden-import=pyqtgraph.graphicsItems.ViewBox.axisCtrlTemplate_pyqt5',
    '--hidden-import=pyqtgraph.graphicsItems.PlotItem.plotConfigTemplate_pyqt5',
    '--hidden-import=pyqtgraph.imageview.ImageViewTemplate_pyqt5',
    '--add-data=%s%s%s' % (os.path.join(PATH_TO_PYQTGRAPH_ICONS, '*.png'), OS_OPERATOR, os.path.join('pyqtgraph', 'icons')),
    '--add-data=%s%s%s' % (os.path.join(PATH_TO_PYQTGRAPH_ICONS, '*.svg'), OS_OPERATOR, os.path.join('pyqtgraph', 'icons')),
    '--clean',
    '--noconfirm',
    # '--debug=all',
    '--windowed',
    os.path.join('inlinino', '__main__.py')
])
