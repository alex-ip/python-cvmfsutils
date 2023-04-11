#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created by René Meusel
This file is part of the CernVM File System auxiliary tools.
"""

import datetime
import collections
import hashlib
import os


from _common import _split_md5, DatabaseObject
from dirent  import DirectoryEntry, Chunk


class CatalogIterator:
    """ Iterates through all directory entries of a Catalog """

    def __init__(self, catalog):
        self.catalog = catalog
        self.backlog = collections.deque()
        root_path = ""
        if not self.catalog.is_root():
            root_path = self.catalog.root_prefix
        self._push((root_path, self.catalog.find_directory_entry(root_path)))


    def __iter__(self):
        return self


    def next(self):
        if not self._has_more():
            raise StopIteration()
        return self._recursion_step()


    def _has_more(self):
        return len(self.backlog) > 0


    def _push(self, path):
        self.backlog.append(path)


    def _pop(self):
        return self.backlog.pop()


    def _recursion_step(self):
        path, dirent = self._pop()
        if dirent.is_directory():
            new_dirents = self.catalog.list_directory_split_md5(dirent.md5path_1, \
                                                                dirent.md5path_2)
            for new_dirent in new_dirents:
                self._push((path + "/" + new_dirent.name, new_dirent))
        return path, dirent



class CatalogReference:
    """ Wraps a catalog reference to nested catalogs as found in Catalogs """

    def __init__(self, root_path, clg_hash, clg_size = 0):
        self.root_path = root_path.encode('utf8')
        self.hash      = clg_hash
        self.size      = clg_size

    def __str__(self):
        return "<CatalogReference for " + self.root_path + " - " + self.hash + ">"

    def __repr__(self):
        return "<CatalogReference for " + self.root_path + ">"

    def retrieve_from(self, source_repository):
        return source_repository.retrieve_catalog(self.hash)



class CatalogStatistics:
    """ Provides a convenience data wrapper around catalog statistics """

    def __init__(self, catalog):
        self.catalog = catalog
        if catalog.schema >= 2.1:
            self._read_statistics(catalog)

    def __str__(self):
        return "<CatalogStatistics for " + self.catalog.root_prefix + ">"

    def __repr__(self):
        return self.__str__()


    def num_entries(self):
        return self._get_stat('regular') + \
               self._get_stat('dir')     + \
               self._get_stat('symlink')

    def num_subtree_entries(self):
        return self._get_stat('all_regular') + \
               self._get_stat('all_dir')     + \
               self._get_stat('all_symlink')

    def num_chunked_files(self):
        return self._get_stat('chunked')

    def num_subtree_chunked_files(self):
        return self._get_stat('all_chunked')

    def num_file_chunks(self):
        return self._get_stat('chunks')

    def num_subtree_file_chunks(self):
        return self._get_stat('all_chunks')

    def data_size(self):
        return self._get_stat('file_size')

    def subtree_data_size(self):
        return self._get_stat('all_file_size')

    def get_all_fields(self):
        return self._get_stat('all_regular') , self._get_stat('all_dir') ,          \
               self._get_stat('all_symlink') , self._get_stat('all_file_size') ,    \
               self._get_stat('all_chunked') , self._get_stat('all_chunked_size') , \
               self._get_stat('all_chunks')  , self._get_stat('all_nested')


    def _read_statistics(self, catalog):
        stats = catalog.run_sql("SELECT * FROM statistics ORDER BY counter;")
        for stat, value in stats:
            if stat.startswith('self_'):
                setattr(self, stat[5:], value)
            elif stat.startswith('subtree_'):
                setattr(self, "all_" + stat[8:], value + getattr(self, stat[8:]))


    def _get_stat(self, stat):
        if not hasattr(self, stat):
            raise Exception("Statistic '" + stat + "' not provided.")
        return getattr(self, stat)



class Catalog(DatabaseObject):
    """ Wraps the basic functionality of CernVM-FS Catalogs """

    @staticmethod
    def open(catalog_path):
        """ Initializes a Catalog from a local file path """
        f = open(catalog_path)
        return Catalog(f)

    def __init__(self, catalog_file, catalog_hash = ""):
        DatabaseObject.__init__(self, catalog_file)
        self.hash = catalog_hash
        self._read_properties()
        self._guess_root_prefix_if_needed()
        self._guess_last_modified_if_needed()
        self._check_validity()


    def __str__(self):
        return "<Catalog " + self.root_prefix + ">"


    def __repr__(self):
        return self.__str__()


    def __iter__(self):
        return CatalogIterator(self)


    def has_nested(self):
        return self.nested_count() > 0


    def nested_count(self):
        """ Returns the number of nested catalogs in this catalog """
        num_catalogs = self.run_sql("SELECT count(*) FROM nested_catalogs;")
        return num_catalogs[0][0]


    def list_nested(self):
        """ List CatalogReferences to all contained nested catalogs """
        new_version = (self.schema <= 1.2 and self.schema_revision > 0)
        if new_version:
            sql_query = "SELECT path, sha1, size FROM nested_catalogs;"
        else:
            sql_query = "SELECT path, sha1 FROM nested_catalogs;"
        catalogs = self.run_sql(sql_query)
        if new_version:
            return [ CatalogReference(clg[0], clg[1], clg[2]) for clg in catalogs ]
        else:
            return [ CatalogReference(clg[0], clg[1]) for clg in catalogs ]


    def get_statistics(self):
        """ returns the embedded catalog statistics (if available) """
        return CatalogStatistics(self)

    def _path_sanitized(self, needle_path, nested_path):
        """
        Checks if one of the siblings of the path is a nested catalog and
        contains the same initial characters
        """
        return len(needle_path) == len(nested_path) or \
            (len(needle_path) > len(nested_path) and
                needle_path[len(nested_path)] == '/')

    def find_nested_for_path(self, needle_path):
        """ Find the best matching nested CatalogReference for a given path """
        nested_catalogs  = self.list_nested()
        best_match       = None
        best_match_score = 0
        real_needle_path = self._canonicalize_path(needle_path)
        for nested_catalog in nested_catalogs:
            if real_needle_path.startswith(nested_catalog.root_path) and    \
               len(nested_catalog.root_path) > best_match_score and         \
                self._path_sanitized(real_needle_path,
                                     nested_catalog.root_path):
                    best_match_score = len(nested_catalog.root_path)
                    best_match       = nested_catalog
        return best_match


    def list_directory(self, path):
        """ Create a directory listing of the given directory path """
        real_path = self._canonicalize_path(path)
        if real_path == '/':
            real_path = ''
        parent_1, parent_2 = _split_md5(hashlib.md5(real_path).digest())
        return self.list_directory_split_md5(parent_1, parent_2)


    def list_directory_split_md5(self, parent_1, parent_2):
        """ Create a directory listing of DirectoryEntry items based on MD5 path """
        res = self.run_sql("SELECT " + DirectoryEntry.catalog_db_fields() + " \
                            FROM catalog                                       \
                            WHERE parent_1 = " + str(parent_1) + " AND         \
                                  parent_2 = " + str(parent_2) + "             \
                            ORDER BY name ASC;")
        for result in res:
            yield self._make_directory_entry(result)


    def find_directory_entry(self, path):
        """ Finds the DirectoryEntry for a given path """
        real_path = self._canonicalize_path(path)
        print(f'real_path = {real_path}')
        md5path = hashlib.md5(real_path)
        return self.find_directory_entry_md5(md5path)


    def find_directory_entry_md5(self, md5path):
        """ Finds the DirectoryEntry for a given MD5 hashed path """
        lo, hi = _split_md5(md5path.digest())
        return self.find_directory_entry_split_md5(lo, hi)


    def find_directory_entry_split_md5(self, md5path_1, md5path_2):
        """ Finds the DirectoryEntry for the given split MD5 hashed path """
        res = self.run_sql("SELECT " + DirectoryEntry.catalog_db_fields() + " \
                            FROM catalog                                      \
                            WHERE md5path_1 = " + str(md5path_1) + " AND      \
                                  md5path_2 = " + str(md5path_2) + "          \
                            LIMIT 1;")
        return self._make_directory_entry(res[0]) if len(res) == 1 else None

    def backtrace_path_split_md5(self, md5path_1, md5path_2):
        """ finds the file path associated with a given MD5 hash """
        catalog_root_path = self.root_prefix if self.root_prefix != "/" else ""
        root_md5_hash     = _split_md5(hashlib.md5(catalog_root_path).digest())
        result = ""
        while True:
            res = self.run_sql("SELECT parent_1, parent_2, name          \
                                FROM catalog                             \
                                WHERE md5path_1 = " + str(md5path_1) + " \
                                  AND md5path_2 = " + str(md5path_2) + ";")
            if len(res) != 1:
                break

            md5parent_1, md5parent_2 = res[0][0], res[0][1]
            if md5parent_1 == root_md5_hash[0] and \
               md5parent_2 == root_md5_hash[1]:
                break

            result = res[0][2] + ("/" + result if result != "" else "")
            md5path_1 = md5parent_1
            md5path_2 = md5parent_2
        return self.root_prefix + result if result != "" else None

    def backtrace_content_hash(self, content_hash):
        """ Try to find file paths that reference a given content hash """
        # TODO(rmeusel): currently this only works for SHA-1 content hashes
        bulk_chunks = self.run_sql("SELECT md5path_1, md5path_2 \
                                    FROM catalog                \
                                    WHERE lower(hex(hash)) = '" +
                                                            content_hash + "';")
        partial_chunks = self.run_sql("SELECT md5path_1, md5path_2 \
                                       FROM chunks                 \
                                       WHERE lower(hex(hash)) = '" +
                                                            content_hash + "';")
        pairs = []
        for md5pair in bulk_chunks + partial_chunks:
            pairs.append(self.backtrace_path_split_md5(md5pair[0], md5pair[1]))

        return pairs


    def is_root(self):
        """ Checks if this is the root catalog (based on the root prefix) """
        return self.root_prefix == "/"


    def has_predecessor(self):
        return hasattr(self, "previous_revision")


    def get_predecessor(self):
        if not self.has_predecessor():
            return None
        return CatalogReference(self.root_prefix, self.previous_revision)


    def _read_properties(self):
        self.read_properties_table(lambda prop_key, prop_value:
            self._read_property(prop_key, prop_value))
        if not hasattr(self, 'schema_revision'):
            self.schema_revision = 0

    def _read_property(self, prop_key, prop_value):
        """ Detect catalog properties and store them as public class members """
        if prop_key == "revision":
            self.revision          = prop_value
        if prop_key == "schema":
            self.schema            = float(prop_value)
        if prop_key == "schema_revision":
            self.schema_revision   = float(prop_value)
        if prop_key == "last_modified":
            self.last_modified     = datetime.datetime.fromtimestamp(int(prop_value))
        if prop_key == "previous_revision":
            self.previous_revision = prop_value
        if prop_key == "root_prefix":
            self.root_prefix       = prop_value


    def _make_directory_entry(self, result_set):
        dirent = DirectoryEntry(result_set)
        self._read_chunks(dirent)
        return dirent


    def _read_chunks(self, dirent):
        """ Finds and adds the file chunk of a DirectoryEntry """
        if self.schema < 2.4:
            return
        res = self.run_sql("SELECT " + Chunk.catalog_db_fields() + "            \
                            FROM chunks                                         \
                            WHERE md5path_1 = " + str(dirent.md5path_1) + " AND \
                                  md5path_2 = " + str(dirent.md5path_2) + "     \
                            ORDER BY offset ASC;")
        dirent._add_chunks(res)


    def _guess_root_prefix_if_needed(self):
        """ Root catalogs don't have a root prefix property (fixed here) """
        if not hasattr(self, 'root_prefix'):
            self.root_prefix = "/"


    def _guess_last_modified_if_needed(self):
        """ Catalog w/o a last_modified field, we set it to 0 """
        if not hasattr(self, 'last_modified'):
            self.last_modified = datetime.datetime.min

    def find_best_child_for_path(self, path):
        """
        Finds the best fit for a given path between a catalog's children
        :param path: path to find
        :return: the closest catalog-child to a given path
        """
        max_length = 0
        best_fit = None
        for cr in self.list_nested():
            curr_length = path.find(cr.root_path)
            if curr_length == 0 and len(cr.root_path) > max_length:
                best_fit = cr
                max_length = len(cr.root_path)
        return best_fit


    @staticmethod
    def _canonicalize_path(path):
        if not path:
            return "".encode('utf8')
        return os.path.abspath(path).encode('utf8')


    def _check_validity(self):
        """ Check that all crucial properties have been found in the database """
        if not hasattr(self, 'revision'):
            raise Exception("Catalog lacks a revision entry")
        if not hasattr(self, 'schema'):
            raise Exception("Catalog lacks a schema entry")
        if not hasattr(self, 'root_prefix'):
            raise Exception("Catalog lacks a root prefix entry")
        if not hasattr(self, 'last_modified'):
            raise Exception("Catalog lacks a last modification entry")


