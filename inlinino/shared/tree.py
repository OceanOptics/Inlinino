from inlinino.shared.file_utils import sizeof_fmt

class QGenericItem:
    def __init__(self, data):
        self._data = data
        if type(data) == tuple:
            self._data = list(data)
        if type(data) is str or not hasattr(data, '__getitem__'):
            self._data = [data]
        self._column_count = len(self._data)
        self._children = []
        self._parent = None
        self._row = 0

    def data(self, column):
        if 0 <= column < len(self._data):
            return self._data[column]

    def columnCount(self):
        return self._column_count

    def childCount(self):
        return len(self._children)

    def child(self, row):
        if 0 <= row < self.childCount():
            return self._children[row]

    def parent(self):
        return self._parent

    def row(self):
        return self._row

    def addChild(self, child):
        child._parent = self
        child._row = len(self._children)
        self._children.append(child)
        self._column_count = max(child.columnCount(), self._column_count)


class QFileItem(QGenericItem):
    HEADER = ('Name', 'Size', 'Kind', 'Date Modified')

    def __init__(self, name: str, is_dir: bool, size: int = -1, date: str = ''):
        self.name, self.is_dir, self.size, self.date = name, is_dir, size, date
        self.is_listed = False
        self._children = []
        self._parent = None
        self._row = 0

    @classmethod
    def from_line(cls, line: str):
        """
        Example of line supported:
                       Size (bytes)           Date Time     Name
                                512 2021-10-27 12:51:14     CONFIG.BCK
            Dir                   0 2028-00-00 00:00:00     FREEFALL

        :param line:
        :return:
        """
        s = line.split('\t')
        return cls(s[3], s[0].lower() == 'dir', int(s[1]), s[2])

    def __repr__(self):
        return f"<{'Folder' if self.is_dir else 'File'} {self.name}>"

    @property
    def files(self) -> list:
        return self._children

    @property
    def files_names(self) -> set:
        return [child.name for child in self._children]

    def add_files(self, files: list):
        """
        Prefer this method over addChild to append files to directory
        :param files: list of QFileItem
        :return:
        """
        if not self.is_dir:
            raise ValueError('Not a directory, unable to add files.')
        for file in files:
            if file.name not in self.files_names:  # Compare on file name as member variables could differ (e.g. listed)
                self.addChild(file)
        self.is_listed = True

    def path(self):
        if self._parent is None:
            return [self.name]
        return self._parent.path() + [self.name]

    def data(self, column):
        if column == 0:
            return self.name
        elif column == 1:
            return '--' if self.is_dir else (sizeof_fmt(self.size) if self.size != -1 else 'NA')
        elif column == 2:
            return 'Folder' if self.is_dir else 'File'
        elif column == 3:
            return self.date

    def columnCount(self):
        return 4

    def addChild(self, child):
        child._parent = self
        child._row = len(self._children)
        self._children.append(child)
