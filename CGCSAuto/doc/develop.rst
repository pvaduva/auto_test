Automated Test Development
===============================================

Create Local Work Branch
-----------------------------------------------
Goto automation repo. If you haven't checked out any branch, it will be under master by default.
::

    export $MY_REPO=path_to_wassp-repos/testcase/cgcs
    cd $MY_REPO
    cd CGCSAuto

Ignore the changes to .idea folder
::

    # This only needs to be done once
    git update-index --assume-unchanged CGCSAuto/.idea/*

Setup the remote URL
::

    # This only needs to be done once.
    git remote set-url origin ssh://<your_username>@git.wrs.com/git/projects/wassp-repos/testcases/cgcs

Work off a local branch that was checked out from develop branch
::

    # Checkout a local develop branch which automatically tracks the remote develop branch
    git checkout develop     
    # Create a new local branch off develop to start your work
    git checkout -b <your work branch name>

Now you can start make code changes on the local branch, make sure your TEST your change before next step. If your code is not testable yet, make sure you inform the reviewers about the situation and run a sample test case just to ensure the framework is not broken.

Code Review
-----------------------------------------------
After you've made your code changes, you'll need to commit them locally, and send them for code review using Code Collaborator

* Note that normally we should do code review **before** push to remote branch.

::

 # Check your changes
 git status
 # Add only files that are ready to be commited. e.g., the ones that are code reviewed.
 git add <files_to_be_commited>  (or 'git add -u' to add all but untracked files)
 git commit (or 'git commit --amend' if it's a revision of an existing commit)
 # Add your commit messages and save the changes


* Launch code collaborator client: /folk/cm/bin/codecollaborator/linux/ccollabgui
* Choose Add Unpushed Commits..., then either create a new review, or add to an existing review if it's a revision after the initial review.
* Add reviewers to your review via the http://codereview.wrs.com/ui website.

   * Reviewers should include at least one automation specialist and one domain specialist
* More info about: Code Collaborator: http://twiki.wrs.com/Main/CCollabQuickstart

Push Your Change to Remote Repo
-----------------------------------------------
::

 # pull changes from lastest develop branch
 git checkout develop
 git pull origin develop
 # Rebase your changes to lastest content of develop branch to avoid conflict when pushing
 git checkout <your work branch>
 git rebase develop
 # If any conflict happened, fix the conflicts locally before before continue.
 git push origin <your work branch>:develop

You should receive an email indicating your change is pushed to the develop branch in ``testcases/cgcs`` repo

Check on git that your change is there. ``http://git/cgi-bin/cgit.cgi/projects/wassp-repos/testcases/cgcs/commit/?h=develop``

Automated Test Execution
-----------------------------------------------

* Scheduled formal sanity/reregression test should be excuted on master branch.
* develop branch will be merged with master branch on a regular basis or on demand by automation specialist.

cd to wasp-repos/testcases/cgcs/CGCSAuto directory Sample Commands to Run Test Cases::

 # Run all P1 testcases
 py.test -m P1
 # Run P2 or P3 test cases in a test_sample.py module
 py.test -m 'P1 or P2' testcases/test_sample.py
 # Run tests in test_sample module with ping_vms in tests' names
 py.test -k 'ping_vms' testcases/test_sample.py
