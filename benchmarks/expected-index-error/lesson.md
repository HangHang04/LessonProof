# 读懂列表越界的错误信息

## 学习目标

通过一个有意写错的例子，找到报错函数、访问位置和异常类型。

## 环境与材料

目标环境为 Python 3.11.15，使用标准库。
在课程包根目录打开 `lesson.ipynb`，新建内核，依次执行代码格。
这节课不需要额外数据文件。第一格应当报错；观察完错误后，手动继续第二格。

## 步骤 observe-error

执行函数 `favorite_ice_cream()`。列表有三个元素，代码尝试取索引 3。
观察 `IndexError`，错误信息包含 `list index out of range`。
保留这一格中的错误访问，它用于演示如何读 traceback。

## 步骤 explain-index

继续执行第二格，查看同样三个元素的列表长度和最后一个有效索引。
输出 JSON `{"item_count": 3, "last_valid_index": 2}`。
说明为什么三个元素的列表不能读取索引 3。

## 来源

派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。
原课：[Errors and Exceptions](https://github.com/swcarpentry/python-novice-inflammation/blob/a765c2c50b91d7618f803e12c23eef6607db2390/episodes/09-errors.md)。第一格保留原课函数，第二格为本包添加的理解检查。
