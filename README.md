# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/jic-dtool/dtool-dserver/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                            |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------- | -------: | -------: | ------: | --------: |
| dtool\_dserver/\_\_init\_\_.py  |       10 |        4 |     60% |5-6, 10-12 |
| dtool\_dserver/auth.py          |      163 |       13 |     92% |66-67, 186, 205, 216-217, 226-228, 256, 280-281, 292 |
| dtool\_dserver/cli.py           |       76 |        2 |     97% |    37, 94 |
| dtool\_dserver/connection.py    |       31 |        0 |    100% |           |
| dtool\_dserver/errors.py        |        8 |        0 |    100% |           |
| dtool\_dserver/storagebroker.py |      378 |       53 |     86% |33-34, 212-213, 225, 271, 370-377, 382-388, 395, 405, 441, 484-487, 517-520, 556-561, 567, 599-600, 604-605, 664, 672, 676, 680, 684, 688, 692, 696, 700, 741-742 |
| **TOTAL**                       |  **666** |   **72** | **89%** |           |


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