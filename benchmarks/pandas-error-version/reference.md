# 异常名称与环境不一致：验收依据

证据状态：历史修订前后内容、数据子集与 pandas 官方文档已核对；本包尚待隔离环境试跑。
这是公开历史问题的缩小改编基准，不代表当前上游课程仍存在这个问题。

## 应发现的问题

预期 1 项：`cast-weight` 步骤的讲义异常名称与所声明的 pandas 2.2.3 环境不一致。
类别：`lesson_environment_mismatch`。讲义声称 `ValueError: Cannot convert NA to integer`，目标环境对应 `IntCastingNaNError`。
后续诊断应引用讲义段落、实际运行时版本和异常记录；本阶段只是保存答案依据，尚未自动发现该问题。

## 修复应达到什么结果

建议修正讲义的名称及消息，说明旧版可能显示 ValueError，保留观察缺失值转换失败的任务。
不要通过删掉缺失行、填 0、捕获后隐藏异常或删除转换步骤来消除教学内容。
修复前后的代码运行本来就应符合相同的 `acceptance.json`；代码验收通过本身不能证明讲义问题已修复。
讲义修订还需单独人工核对这一项问题是否解决。修改参考答案或验收目标不能代替修复。

## 原始证据

- [问题 #549](https://github.com/datacarpentry/python-ecology-lesson/issues/549)和[合并修订 #571](https://github.com/datacarpentry/python-ecology-lesson/pull/571/files)，修订于 2023-06-05 合并。
- 修订前完整版本：`728c22a29a9089ea0cd73d54bde3f3e82cf2849f`；修订后：`acb60886d7bb0c7d4e914ecc562d7d9d0afed2bd`。
- `upstream-before.md` 与 `upstream-after.md` 保存两版同一位置第 270–292 行；原始文件 SHA-256 及网址在 course.json 中。
- 原始两份完整讲义的差异就是正文的异常说明；示例代码未改变。原先代码输出已经写成 IntCastingNaNError，正文仍使用旧名称。
- [pandas 2.2.3 官方异常说明](https://pandas.pydata.org/pandas-docs/version/2.2.3/reference/api/pandas.errors.IntCastingNaNError.html)确认含 NaN 的数组转整数对应 IntCastingNaNError。此文档证据不能替代课程实跑。

## 数据与改编

原始 surveys.csv 的 SHA-256 为 `0b4ad06161ed67d5a1d5ae418a6ed6d76a684207e40c747b6fc5cfba53e93116`。
选取 record_id 为 1、2、63、64、65 的记录，体重分别为空、空、40、48、29；字段和值不变，CSV 换行统一为 LF。
数据来自 [Portal Project Teaching Database](https://doi.org/10.6084/m9.figshare.1314459)，许可为 [CC0](https://creativecommons.org/publicdomain/zero/1.0/)。取样版本由 Data Carpentry 的固定提交确定。
讲义翻译保留原来的过时名称，增加明确的现代环境、准备步骤和缺失记录检查。验收目标按上游修订与官方文档独立确定。
派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。

## 评测使用

仅 `learner_files` 交给被测系统。验收标准、修订后的讲义节选、问题记录和本文件留在评测侧。
三套公开样本属于开发基准；正式泛化评测应另选没有用于开发的课程。
