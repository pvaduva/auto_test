Installation
===============================================

Ubuntu 14.04 or higher. Windows is not supported

Requirements
-----------------------------------------------

 * Python3.4 or higher::

    sudo apt-get install python3
 * Pip for Python 3::

    sudo apt-get install python3-pip
 * Pexpect for python3::

    sudo pip3 install pexpect
 * Pytest for python3::

    sudo pip3 install pytest

Code Collaborator Setups
-----------------------------------------------
 * Launch code collaborator client from ``/folk/cm/bin/codecollaborator/linux/ccollabgui``
 * From **File > Preferences:**

   * Add Server ``URL: http://codereview.wrs.com``
   * Add ``Username: <your_windows_username>``
   * Press **Test Connection** and enter your Windowns password when prompted.
   * Press **OK**
 * Add repo to Code Collaborator va **Add...**:

   * Local Source Code Location: Browse to ``wassp-repos/testcases/cgcs/CGCSAuto`` directory and press OK
   * SCM: Select **Git**
   * Git Executable: enter your git executable path. such as ``/usr/bin/git``
   * Press **Validate** You should see that the under **Configuration**, GIT_DIR is automatically updated to the ``wassp-repos/testcases/cgcs`` repo
   * Press **OK**

Pycharm 
-----------------------------------------------

IDE is highly recommended for formating checking, auto generating doc strings, and easy navigations between functions, modules, etc.

If you decide not to use IDE, please either enable PEP-8 check on your editor or install PEP-8 Git Commit Hook (https://github.com/cbrueffer/pep8-git-hook)

Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Official Installation instruction: ``https://www.jetbrains.com/pycharm/download/#section=linux``

Install with PPA or umake: ``http://itsfoss.com/install-pycharm-ubuntu/``

Setup
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
 * Open ``wassp-repos/testcases/cgcs/CGCSAuto`` folder from pycharm
 * Add **CGCSAuto** folder to Content Root when prompted, or from **Settings > Project: CGCSAuto > Project Structure**

   * This is for discovery of CGCSAuto modules within pycharm. If this is not set, CGCSAuto libaries will not be recognized by pycharm.
 * Set python interpretor to python3.4 when prompted, or from **Settings > Project: CGCSAuto > Project Interpreter**

   * This is to ensure the error checkings, lib discovery and such will be based on Python3.4.
 * Set doc string format to Google from **Settings > Tools > Python Integrated Tools > Docstrings > Docstring format**
 * Show Members of a python module: From Project tools window (usually column on the left) > click the settings icon, and choose Show Members

   * This is for easy navigation to a function, class or member variable inside a module. This is useful when module is long such as some keyword modules
 * Other Tips:

   * Search any text within the scope of project: ``ctrl+shift+f``
   * Search a file by its name: ``ctrl+shift+n``

