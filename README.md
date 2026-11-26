# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/jic-dtool/dtool-dserver/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| dtool\_dserver/\_\_init\_\_.py  |       10 |        4 |     60% |5-6, 10-12 |
| dtool\_dserver/auth.py          |      245 |       10 |     96% |68-69, 241, 260, 271-272, 412, 436-437, 448 |
| dtool\_dserver/cli.py           |      109 |        2 |     98% |    30, 37 |
| dtool\_dserver/connection.py    |       38 |        0 |    100% |           |
| dtool\_dserver/errors.py        |        8 |        0 |    100% |           |
| dtool\_dserver/storagebroker.py |      397 |       54 |     86% |33-34, 90-91, 114, 122, 291, 390-397, 402-408, 415, 425, 461, 504-507, 537-540, 576-581, 587, 619-620, 624-625, 684, 692, 696, 700, 704, 708, 712, 716, 720, 755, 764 |
| **TOTAL**                       |  **807** |   **70** | **91%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/jic-dtool/dtool-dserver/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/jic-dtool/dtool-dserver/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/jic-dtool/dtool-dserver/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/jic-dtool/dtool-dserver/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fjic-dtool%2Fdtool-dserver%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/jic-dtool/dtool-dserver/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.