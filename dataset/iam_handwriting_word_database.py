import os
from os.path import isfile

from lxml import etree

import torch
from PIL import Image
from torch.utils.data.dataset import Dataset

from utils.image import image_pillow_to_numpy


class IAMHandwritingWordDatabase(Dataset):

    def __init__(self, path, height=32, loss=None):
        self.height = height
        self.loss = loss

        self.images_path = os.path.join(path, "words")
        self.xmls_path = os.path.join(path, "xml")

        for xml_name in os.listdir(self.xmls_path):
            self.parse_xml(os.path.join(self.xmls_path, xml_name))

    def parse_xml(self, xml_path):
        tree = etree.parse(xml_path)
        self.parse_xml_tree(xml_path, tree.getroot())

    def parse_xml_tree(self, xml_path, root):

        for children in root.getchildren():
            if children.tag.title() == "Line":
                root_dict = {}
                for name, value in children.attrib.items():
                    root_dict[name] = value

                self.parse_xml_tree_line(children)
            else:
                self.parse_xml_tree(xml_path, children)

    def parse_xml_tree_line(self, root):
        text_lines = []

        for children in root.getchildren():
            if children.tag.title() == "Word":
                text, id = self.parse_xml_tree_word(children)

                ids = id.split("-")
                image_path = os.path.join(self.images_path,
                                          ids[0] + "/" + ids[0] + "-" + ids[1] + "/" + ids[0] + "-" + ids[1] + "-" +
                                          ids[2] + "-" + ids[3] + ".png")

                if isfile(image_path):
                    try:
                        image = Image.open(image_path)
                        self.labels.append((id, text))
                    except Exception:
                        pass

    def parse_xml_tree_word(self, root):
        root_dict = {}
        for name, value in root.attrib.items():
            root_dict[name] = value

        return root_dict["text"], root_dict["id"]

    def get_corpus(self):
        corpus = ""
        for id, text in self.labels:
            if corpus == "":
                corpus = text
            else:
                corpus = corpus + ". " + text
        return corpus

    def __getitem__(self, index):
        id, text = self.labels[index]
        ids = id.split("-")
        image_path = os.path.join(self.images_path, ids[0] + "/" + ids[0] + "-" + ids[1] + "/" + ids[0] + "-" + ids[1] + "-" + ids[2] + "-" + ids[3] + ".png")

        # Load the image
        image = Image.open(image_path).convert('RGB')
        width, height = image.size

        image = image.resize((width * self.height // height, self.height), Image.ANTIALIAS)

        image = image_pillow_to_numpy(image)

        return torch.from_numpy(image), (self.loss.preprocess_label(text, width * self.height // height), text, image.shape[2])

    def __len__(self):
        return len(self.labels)
