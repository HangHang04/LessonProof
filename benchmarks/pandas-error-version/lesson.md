# 缺失值与整数转换

## 学习目标

观察缺失体重数据转为整数时的错误，并定位缺失记录。

## 环境与材料

目标环境为 Python 3.11.15、pandas 2.2.3、NumPy 1.26.4。由教师预先准备环境。
在课程包根目录打开 `lesson.ipynb`，新建内核，按顺序执行。
输入为 `data/surveys.csv`，首行为字段名；`record_id` 标识记录，`weight` 表示体重，空单元格表示缺失。
本包从原数据选取 record_id 为 1、2、63、64、65 的五条记录，保留所有字段和原始值。

## 步骤 load-surveys

导入 pandas 和标准库 json，用 `pandas.read_csv` 读取数据到 `surveys_df`。
本步骤完成后没有输出。

## 步骤 cast-weight

尝试执行 `surveys_df['weight'].astype('int')`，观察 pandas 对缺失值的处理。
讲义说明：此处抛出 `ValueError: Cannot convert NA to integer`。
本练习需要观察转换失败的原因；保留缺失值和该转换操作。

## 步骤 inspect-missing

观察错误后继续下一格，找出体重缺失的 `record_id`。
输出 JSON，字段 `missing_weight_record_ids` 为 `[1, 2]`，`rows` 为 `5`。

## 来源

派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。
本包选取 [Data Types and Formats](https://github.com/datacarpentry/python-ecology-lesson/blob/728c22a29a9089ea0cd73d54bde3f3e82cf2849f/episodes/04-data-types-and-format.md) 的缺失值转换练习；运行环境由本包指定。
数据来自 [Portal Project Teaching Database](https://doi.org/10.6084/m9.figshare.1314459)，按 CC0 提供。本包的数据快照及选行说明见 course.json。
