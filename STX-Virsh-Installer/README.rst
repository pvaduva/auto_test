# STX-Virsh-Installer

This project can be used to install StarlingX system on Qemu-KVM.
Supported StarlingX system mode:
- Simplex
- Duplex
- Standard
- Storage

Detailed information about StarlingX system can be found from link:
[Installation and Deployment Guides](https://docs.starlingx.io/deploy_install_guides/index.html)

## Prerequisites

- python > 3.2, <= 3.7.2
- pexpect
- paramiko
- Operating System: Freshly installed Ubuntu 16.04 LTS 64-bit
- Proxy settings configured (if applies)
- Git
- KVM/VirtManager
- Libvirt library
- QEMU full-system emulation binaries
- tools project

## Installing
- Install python3
```bash
$ sudo apt-get install python3
```
- Install pexpect
```bash
$ sudo pip3 install pexpect
```
- Install paramiko
```bash
$ sudo pip3 install paramiko
```

- [Setting up the workstation](https://docs.starlingx.io/deploy_install_guides/upcoming/aio_simplex.html#setting-up-the-workstation)
```bash
$ sudo apt-get update
$ cd $HOME
$ git clone https://opendev.org/starlingx/tools
$ cd $HOME/tools/deployment/libvirt/
$ bash install_packages.sh
```

## Usage

Set /path/to/stx-virsh-installer as working directory.
To install StarlingX system with template file and default setup, execute:
```bash
SYSTEM_MODE="simplex"
python3 -m installer -m $SYSTEM_MODE
```

To delete the installed StarlingX system, execute:
```bash
SYSTEM_MODE="simplex"
python3 -m installer -m $SYSTEM_MODE -d
```

SYSTEM_MODE should be one of: simplex, duplex, standard or storage.

To install StarlingX system with custom settings:
	- Modify the variable.ini file.
	- Use -o /path/to/overwrite_file after the default installation command
	- Use -c /path/to/custom_files_directory after the default installation command to install StarlingX system with custom files that will not be dynamically modified by stx-virsh-installer
	- Use -t /path/to/custom_template_files_directory after the default installation command to install StarlingX system with custom template files that will be dynamically modified by stx-virsh-installer
> Please check variable.ini for detailed information about overwriting custom variables and providing custom files


