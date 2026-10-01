# 图书借阅数据分析

来源：LessonProof 项目原创教学样例，数据为人工编写的开发数据。

## 学习目标

用 Python 标准库读取 CSV，区分书籍库存与借阅次数，计算本批记录的书籍种类数和借阅总次数。

## 环境与文件

Python 3.10 或更新版本。将 `lesson.ipynb` 与 `loans.csv` 放在同一工作目录，使用新内核按顺序执行 Notebook。

`loans.csv` 的三列为：`title`（书名）、`borrow_count`（借阅次数）、`stock_count`（库存数量）。

## 步骤 load-data

读取 UTF-8 编码的 `loans.csv`，将每一行保存在 `rows` 中。

## 步骤 summarize

统计数据行数，将 `borrow_count` 转换为整数后求和。输出 JSON，包含 `book_count` 和 `total_borrows`。

本样例有 3 种书，借阅总次数为 10。库存总数不属于本步骤的统计目标。

## 验收

两个步骤按顺序执行成功。最终输出为 `{"book_count": 3, "total_borrows": 10}`。
