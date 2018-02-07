%define name python-cvmfsutils
%define version 0.3.3
%define unmangled_version 0.3.3
%define unmangled_version 0.3.3
%define release 1

Summary: Inspect CernVM-FS repositories
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{name}-%{unmangled_version}.tar.gz
License: (c) 2015 CERN - BSD License
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Rene Meusel <rene.meusel@cern.ch>
Requires: python-requests >= 1.1.0 python-dateutil >= 1.4.1
Url: http://cernvm.cern.ch
BuildRequires: python-setuptools

%description
The CernVM-FS python package allows for the inspection of CernVM-FS repositories
using python. In particular to browse their file catalog hierarchy, inspect
CernVM-FS repository manifests (a.k.a. .cvmfspublished files) and the history of
named snapshots inside any CernVM-FS 2.1 repository.

%prep
%setup -n %{name}-%{unmangled_version} -n %{name}-%{unmangled_version}

%build
python setup.py build

%install
python setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES
%defattr(-,root,root)
