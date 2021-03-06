This repository contains the infrastructure for running lightweight checkers on
Ada programs using the Libadalang technology, as well as a set of checkers. For
an example of use of such checkers, see this [blog
post](http://blog.adacore.com/many-more-low-hanging-bugs).

# 1. Code structure

* The adacheck folder contains the framework used to design new lightweight
  checkers
* The checkers folder contains a set of predefined checks based on adacheck

# 2. List of checkers

# 3. License

This code is licensed under GPL v3.

# 4. Build instructions

Download the source of [Libadalang](https://github.com/AdaCore/libadalang) and
follow the instructions given in the README.

# 5. Running the testsuite

In order to run the testsuite, you need to install
[GNATpython](https://github.com/Nikokrock/gnatpython). You can then start it
with the following command-line:

```sh
./run_testsuite.sh
```

This will display the status of all executed testcases as they are executed.
