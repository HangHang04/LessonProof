# 数组分析：验收依据

证据状态：上游材料与数据已核对；课程 Notebook 尚待隔离环境试跑。
这是公开教学片段的开发基准，预期发现的问题为 0。

## 固定目标

三个代码步骤按顺序成功，输出符合 `acceptance.json`。
执行成功却读错文件、跳过第一行、交换行列、计算错结果，均不能据此通过验收。
平均值固定显示为五位小数字符串；这是本包的格式约定，不是通用浮点容差。

## 来源与核对

- [原始讲义](https://github.com/swcarpentry/python-novice-inflammation/blob/a765c2c50b91d7618f803e12c23eef6607db2390/episodes/02-numpy.md)：第 95–100 行读取代码；第 164–200 行形状和索引值；第 296–308 行平均值；第 343–357 行极值。
- 原课给出 60 × 40、首值 0.0、中间值 16.0、平均值 6.14875、最小值 0.0、最大值 20.0。
- 原样数据有 2,400 个整数，总和 14,757。用标准库 CSV 读取和整数求和独立核对，14,757 / 2,400 = 6.14875。此核对不执行课程 Notebook。
- 数据的虚构教学背景见[课程简介](https://swcarpentry.github.io/python-novice-inflammation/)。
- [NumPy 1.26.4 版本说明](https://numpy.org/devdocs/release/1.26.4-notes.html)列出 Python 3.9–3.12 支持范围。3.11.15 是本包选定的后续试跑目标，不是已完成环境验证的声明。

## 改编与使用

保留数据和计算任务，将路径明确为课程根目录下的 `data/`，将输出转为 JSON，并增加稳定步骤 ID。
讲义、Notebook、数据和许可组成学生材料；本文件和验收标准留在评测侧。
派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。
