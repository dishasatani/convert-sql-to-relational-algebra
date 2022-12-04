[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

# Convert SQL to Relational Algebra
A tool that converts given sql to relational algebra.

# Prerequisites
Before you begin you must have Python installed and configured properly for your computer.

Python version: 3.10.8

antlr4-python3-runtime: 4.9.2

To run the project, you need to clone this project to your computer. Link: https://github.com/ahoirg/convert-sql-to-relational-algebra.git

# Run
To run Convert SQL to Relational Algebra, first go to the path where the project is installed in the terminal.

You can run it using the “python .\sql2ra.py "sql_query"” command, then project name.

```python
    $ python .\sql2ra.py "select distinct select_from from MiniHive,Select1 WHERE query='select distinct * from MiniHive where age = 16'"
    
    >> \project_{select_from} (\select_{query = 'select distinct * from MiniHive where age = 16'} (MiniHive \cross Select1))
```
# Running Tests
To run the tests, "python .\test_sql2ra.py" command should be used in the project directory.

```python
python .\test_sql2ra.py

Ran 27 tests in 0.046s

OK
```

# License
This project is licensed under the GNU General Public License v3.0 - see the LICENSE.md file for details
