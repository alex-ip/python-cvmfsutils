#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created by René Meusel
This file is part of the CernVM File System auxiliary tools.

A CernVM-FS repository has essential 'root files' that have a defined name and
serve as entry points into the repository.

Namely the manifest (.cvmfspublished) and the whitelist (.cvmfswhitelist) that
both have class representations inheriting from RootFile and implementing the
abstract methods defined here.

Any 'root file' in CernVM-FS is a signed list of line-by-line key-value pairs
where the key is represented by a single character in the beginning of a line
directly followed by the value. The key-value part of the file is terminted
either by EOF or by a termination line (--) followed by a signature.

The signature follows directly after the termination line with a hash of the
key-value line content (without the termination line) followed by an \n and a
binary string containing the private-key signature terminated by EOF.
"""

import abc
import hashlib

from _exceptions import *


class RootFile:
    """ Base class for CernVM-FS repository's signed 'root files' """

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def _read_line(self, line):
        pass

    @abc.abstractmethod
    def _check_validity(self):
        pass

    @abc.abstractmethod
    def __init__(self, file_object):
        """ Initializes a root file object from a file pointer """
        self.has_signature = False
        for line in file_object.readlines():
            try:
                line = line.decode('utf8')
            except AttributeError:
                pass
            if len(line) == 0:
                continue
            if line[0:2] == "--":
                self.has_signature = True
                break
            self._read_line(line)
        if self.has_signature:
            self._read_signature(file_object)
        self._check_validity()

    @abc.abstractmethod
    def _verify_signature(self, public_entity):
        pass


    def verify_signature(self, public_entity):
        return self.has_signature and self._verify_signature(public_entity)


    @staticmethod
    def _hash_over_content(file_object):
        pos = file_object.tell()
        hash_sum = hashlib.sha1()
        while True:
            line = file_object.readline()
            try:
                line = line.decode('utf8')
            except AttributeError:
                pass
            if line[0:2] == "--":
                break
            if pos == file_object.tell():
                raise IncompleteRootFileSignature("Signature not found")
            hash_sum.update(line.encode('utf8'))
            pos = file_object.tell()
        return hash_sum.hexdigest()


    def _read_signature(self, file_object):
        """ Reads the signature's checksum and the binary signature string """
        file_object.seek(0)
        message_digest = self._hash_over_content(file_object).encode('utf8')

        self.signature_checksum = file_object.readline().rstrip()
        try:
            self.signature_checksum = self.signature_checksum.encode('utf8')
        except AttributeError:
            pass
        print(f'self.signature_checksum = {self.signature_checksum}')
        if len(self.signature_checksum) != 40:
            raise IncompleteRootFileSignature("Signature checksum malformed")
        if message_digest != self.signature_checksum:
            raise InvalidRootFileSignature("Signature checksum doesn't match")
        self.signature = file_object.read()
        try:
            self.signature = self.signature.encode('utf8')
        except AttributeError:
            pass
        if len(self.signature) == 0:
            raise IncompleteRootFileSignature("Binary signature not found")
