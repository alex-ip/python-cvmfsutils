#!/bin/sh

RPMREQUIRES='python-setuptools,python-requests >= 1.1.0,python-dateutil >= 1.4.1' 
set -ex
python setup.py bdist_rpm --requires "$RPMREQUIRES"
# also update spec file for OBS; check it into git manually
python setup.py bdist_rpm --requires "$RPMREQUIRES" --spec-only
mv dist/python-cvmfsutils.spec rpm
