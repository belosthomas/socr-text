#cython: wraparound=False
#cython: boundscheck=False
#cython: cdivision=True

from __future__ import print_function
from __future__ import division
import re
from .prefix_tree cimport PrefixTree


cdef class LanguageModel:
    "unigram/bigram LM, add-k smoothing"

    def __init__(self, corpus, chars, wordChars):
        "read text from filename, specify chars which are contained in dataset, specify chars which form words"

        # read from file
        self.wordCharPattern = '[' + wordChars + ']'
        self.wordPattern = self.wordCharPattern + '+'
        words = re.findall(self.wordPattern, corpus)
        uniqueWords = list(set(words))  # make unique
        self.numWords = len(words)
        self.numUniqueWords = len(uniqueWords)
        self.smoothing = True
        self.addK = 1.0 if self.smoothing else 0.0

        # create prefix tree
        self.tree = PrefixTree()  # create empty tree
        self.tree.addWords(words)  # add all unique words to tree
        self.tree.addWords([w.title() for w in words])
        self.tree.addWords([w.upper() for w in words])

        # list of all chars, word chars and nonword chars
        self.allChars = chars
        self.wordChars = wordChars
        self.nonWordChars = str().join(set(chars) - set(re.findall(self.wordCharPattern, chars)))  # else calculate those chars

        self.lastW1 = None
        self.lastW2 = None
        self.lastProb = None

    cdef getNextWords(self, text):
        "text must be prefix of a word"
        return self.tree.getNextWords(text.lower())

    cdef getNextChars(self, text):
        "text must be prefix of a word"

        if bool(re.match('^[0123456789]+$', text)):
            return "0123456789 "

        nextChars = str().join(self.tree.getNextChars(text.lower()))


        # need to make a get alpha chars with lower probability
        # todo

        # if in between two words or if word ends, add non-word chars
        # if (text == '') or (self.isWord(text)):
        #     nextChars += self.getNonWordChars()
        if text == '':
            nextChars += self.getNonWordChars()
        elif self.isWord(text):
            nextChars += " "

        if bool(re.match('^[XVI]+$', text)):
            for c in "XVI ":
                if text.find(c) < 0:
                    text += c

        return nextChars

    cdef getWordChars(self):
        return self.wordChars + "0123456789"

    cdef getNonWordChars(self):
        return self.nonWordChars

    cdef getAllChars(self):
        return self.allChars

    cdef getWordCharPattern(self):
        return self.wordCharPattern

    cdef isWord(self, text):
        return self.tree.isWord(text)

    cdef getNN(self):
        return self.nnGram

    cdef getBigramProb(self, w1, w2):
        "prob of seeing words w1 w2 next to each other."
        raise NotImplementedError()