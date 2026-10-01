# 数组数据读取与统计

## 学习目标

读取 CSV 数组，理解行列与从 0 开始的索引，计算最小值、最大值和平均值。
数据来自公开课程的虚构炎症试验，60 行代表模拟对象，40 列代表天数。

## 环境与材料

目标环境为 Python 3.11.15、NumPy 1.26.4。由教师预先准备环境。
在课程包根目录打开 `lesson.ipynb`，新建内核，从上到下执行。
输入数据为 `data/inflammation-01.csv`，按逗号分隔，首行就是数据。
Notebook 的三个代码格对应下面三个步骤。原课程选段已整理成中文，步骤输出统一为 JSON。

## 步骤 load-data

导入 NumPy 和标准库 json，使用 `numpy.loadtxt` 读取输入数据并保存到 `data`。
本步骤完成后没有输出。不要将第一行跳过或当作表头。

## 步骤 inspect-array

观察数组形状，以及索引 `[0, 0]`、`[29, 19]` 对应的值。
输出 JSON 字段 `shape`、`first_value`、`middle_value`，分别应为 `[60, 40]`、`0`、`16`。
两个数据值转成 Python 整数以便 JSON 序列化。

## 步骤 summarize

对整个数组计算最小值、最大值和平均值。
输出 JSON 字段 `minimum`、`maximum`、`mean_5dp`，分别应为整数 `0`、整数 `20`、字符串 `"6.14875"`。
平均值使用五位小数的字符串格式；本练习以这个明确的显示精度验收。

## 来源

派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。
原课：[Analyzing Patient Data](https://github.com/swcarpentry/python-novice-inflammation/blob/a765c2c50b91d7618f803e12c23eef6607db2390/episodes/02-numpy.md)。本包的数据文件原样保存。
