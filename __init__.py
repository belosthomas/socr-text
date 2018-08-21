import sys
from configparser import ConfigParser
from random import randint

import numpy as np
import torch
from PIL import Image

from codecs.language.ngram import N2GramAnalyzer
from rating.word_error_rate import levenshtein

from dataset.document_generator_helper import DocumentGeneratorHelper
from models import get_model_by_name
from utils.image import show_pytorch_image
from utils.logger import print_normal, print_warning, print_error
from utils.dataset import parse_datasets_configuration_file
from utils import load_default_datasets_cfg_if_not_exist
from utils.trainer import Trainer


class TextRecognizer:
    """
    This is the main class of the text recognizer
    """

    def __init__(self, model_name="resRnn", lr=0.001, name=None, is_cuda=True):
        """
        Creae a text recognizer with the given models name

        :param model_name: The model name to use
        :param optimizer_name: The optimizer name to use
        :param lr: The learning rate
        :param name: The name where to save the model
        :param is_cuda: True to use cuda
        """
        self.settings = ConfigParser()
        self.settings.read("settings.cfg")

        self.ngram = int(self.settings.get("text", "ngram"))

        if self.ngram == 1:
            print_normal("Using 1-Gram")
            with open("resources/characters.txt", "r") as content_file:
                lst = content_file.read() + " "

            self.labels = {"": 0}
            for i in range(0, len(lst)):
                self.labels[lst[i]] = i + 1

        elif self.ngram == 2:
            print_normal("Using 2-Gram")
            analyser = N2GramAnalyzer()
            analyser.parse_xml_file("resources/texts/fr.xml.gz")
            analyser.parse_xml_file("resources/texts/en.xml.gz")

            self.labels = analyser.get_bests(num=int(self.settings.get("text", "max_gram")))

        else:
            print_error(str(self.ngram) + "-gram not implemented !")
            raise NotImplementedError()

        print(self.labels)

        # with open("resources/word_characters.txt", "r") as content_file:
        #    self.word_labels = content_file.read()

        self.document_helper = DocumentGeneratorHelper()

        self.model = get_model_by_name(model_name)(self.labels)
        self.loss = self.model.create_loss()
        if is_cuda:
            self.model = self.model.cuda()
            self.loss = self.loss.cuda()
        else:
            print_warning("Using the CPU")
            self.model = self.model.cpu()
            self.loss = self.loss.cpu()

        print_normal("Using Adam with a Learning Rate of " + str(lr))
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.trainer = Trainer(self.model, self.loss, self.optimizer, name)

        load_default_datasets_cfg_if_not_exist()
        self.database_helper = DocumentGeneratorHelper()
        self.test_database = parse_datasets_configuration_file(self.database_helper, with_line=True, training=False,
                                                               testing=True,
                                                               args={"height": self.model.get_input_image_height(),
                                                                     "labels": self.labels, "transform": False,
                                                                     "loss": self.loss})
        print_normal("Test database length : " + str(self.test_database.__len__()))

    def train(self, batch_size=1, overlr=None):
        """
        Train the network

        :param overlr: Override the learning rate if specified
        """
        if overlr is not None:
            self.set_lr(overlr)

        train_database = parse_datasets_configuration_file(self.database_helper, with_line=True, training=True,
                                                           testing=False,
                                                           args={"height": self.model.get_input_image_height(),
                                                                 "labels": self.labels, "loss": self.loss}
                                                           )
        # if not os.path.isfile(self.trainer.checkpoint_name + ".corpus"):
        #     with open(self.trainer.checkpoint_name + ".corpus", "w") as corpus:
        #         corpus.write(train_database.get_corpus())

        self.trainer.train(train_database, batch_size=batch_size, callback=lambda: self.trainer_callback(),
                           alternative_loss=lambda x, y: self.alternative_loss(x, y))

    def trainer_callback(self):
        """
        Called during the training to test the network
        :return: The average cer
        """
        self.eval()
        return self.test(limit=32)

    def eval(self):
        """
        Evaluate the model
        """
        self.model.eval()

    def test(self, limit=None):
        """
        Test the network

        :param limit: Limit of images of the test
        :return: The average cer
        """
        is_cuda = next(self.model.parameters()).is_cuda

        loader = torch.utils.data.DataLoader(self.test_database, batch_size=1, shuffle=False, num_workers=1)

        test_len = len(self.test_database)
        if limit is not None:
            test_len = min(limit, test_len)

        wer_s, wer_i, wer_d, wer_n = 0, 0, 0, 0
        cer_s, cer_i, cer_d, cer_n = 0, 0, 0, 0

        sen_err = 0
        count = 0

        for i, data in enumerate(loader, 0):
            image, label = self.test_database.__getitem__(i)
            label = label[1]

            if image.shape[2] < 8:
                continue

            if is_cuda:
                result = self.model(torch.autograd.Variable(image.unsqueeze(0).float().cuda()))
            else:
                result = self.model(torch.autograd.Variable(image.unsqueeze(0).float().cpu()))

            text = self.loss.ytrue_to_lines(result.cpu().detach().numpy())

            # update CER statistics
            _, (s, i, d) = levenshtein(label, text)
            cer_s += s
            cer_i += i
            cer_d += d
            cer_n += len(label)
            # update WER statistics
            _, (s, i, d) = levenshtein(label.split(), split())
            wer_s += s
            wer_i += i
            wer_d += d
            wer_n += len(label.split())
            # update SER statistics
            if s + i + d > 0:
                sen_err += 1

            count = count + 1

            sys.stdout.write("Testing..." + str(count * 100 // test_len) + "%\r")

            if count == test_len:
                break

        cer = (100.0 * (cer_s + cer_i + cer_d)) / cer_n
        wer = (100.0 * (wer_s + wer_i + wer_d)) / wer_n
        ser = (100.0 * sen_err) / count

        print_normal("CER : %.3f; WER : %.3f; SER : %.3f \n" % (cer, wer, ser))
        return wer

    def alternative_loss(self, labels, output):
        label = labels[0][1]
        text = self.loss.ytrue_to_lines(output.cpu().detach().numpy())
        print("")
        print(label)
        print(text)
        print("")
        _, (wer_s, wer_i, wer_d) = levenshtein(label.split(), split())
        return (100.0 * (wer_s + wer_i + wer_d)) / len(label.split())

    def generateandexecute(self, onlyhand=False):
        """
        Generate some images and execute the network on these images

        :param onlyhand: Use only handwritting if true
        """
        is_cuda = next(self.model.parameters()).is_cuda

        while True:
            if not onlyhand:
                image, label = self.test_database.__getitem__(randint(0, len(self.test_database) - 1))
            else:
                image, label = self.test_iam.__getitem__(randint(0, len(self.test_iam) - 1))

            if is_cuda:
                result = self.model(torch.autograd.Variable(image.unsqueeze(0).float().cuda()))
            else:
                result = self.model(torch.autograd.Variable(image.unsqueeze(0).float().cpu()))

            text = self.loss.ytrue_to_lines(result)

            show_pytorch_image(image)

    def recognize(self, images):
        """
        Recognize the text on all the given images

        :param images: The images
        :return: The texts
        """
        is_cuda = next(self.model.parameters()).is_cuda

        height = self.model.get_input_image_height()
        texts = []

        for image in images:
            if image.shape[2] < 64:
                texts.append("")
            else:
                image_channels, image_height, image_width = image.shape
                image = np.resize(image, (image_channels, height, image_width * height // image_height))

                if is_cuda:
                    result = self.model(
                        torch.autograd.Variable(torch.from_numpy(np.expand_dims(image, axis=0))).float().cuda())
                else:
                    result = self.model(
                        torch.autograd.Variable(torch.from_numpy(np.expand_dims(image, axis=0))).float().cpu())

                text = self.loss.ytrue_to_lines(self.lm, result)

                texts.append(text)

        return texts

    def recognize_files(self, files):
        """
        Recognize the text on all the given files

        :param files: The file list
        :return: The texts
        """
        self.eval()
        result = []
        for file in files:
            image = Image.open(file)
            result.append(self.recognize(image)[0])
        return result

    def set_lr(self, lr):
        """
        Override the learning rate

        :param lr: The learning rate
        """
        print_normal("Overwriting the lr to " + str(lr))
        for param_group in self.optimizer.param_groups:
            param_group['lr'] = lr
