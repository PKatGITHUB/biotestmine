import collections

from lxml import etree


class Project:
    def __init__(self, _input):
        self.sources = collections.OrderedDict()
        self.postprocesses = collections.OrderedDict()

        parser = etree.XMLParser(remove_blank_text=True)
        self._projectTree = etree.parse(_input, parser)

        for source_elem in self._projectTree.xpath('/project/sources/source'):
            self.sources[source_elem.attrib['name']] = Source(source_elem)

        for postprocess_elem in self._projectTree.xpath('/project/post-processing/post-process'):
            self.postprocesses[postprocess_elem.attrib['name']] = PostProcess(postprocess_elem)


class Source:
    def __init__(self, elem):
        attrib = elem.attrib

        self.name = attrib['name']
        self.type = attrib['type']

        if 'dump' in attrib:
            self.dump = attrib['dump']
        else:
            self.dump = False


class PostProcess:
    def __init__(self, elem):
        attrib = elem.attrib

        self.name = attrib['name']

        if 'dump' in attrib:
            self.dump = attrib['dump']
        else:
            self.dump = False
