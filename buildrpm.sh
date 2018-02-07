#!/bin/sh

RPMREQUIRES='--build-requires python-setuptools --requires "python-requests >= 1.1.0,python-dateutil >= 1.4.1"' 
set -ex
eval python setup.py bdist_rpm $RPMREQUIRES
# also update spec file for OBS; check it into git manually
eval python setup.py bdist_rpm $RPMREQUIRES --spec-only
mv dist/python-cvmfsutils.spec rpm
