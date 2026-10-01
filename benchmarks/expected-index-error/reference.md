# 列表越界：验收依据

证据状态：上游函数、教学说明和错误示例已核对；本包尚待隔离环境试跑。
这是正常教学行为的公开课程基准，预期发现的课程缺陷为 0。

## 固定目标

第一步必须产生 `IndexError` 且消息包含 `list index out of range`；第二步成功解释长度 3、最后有效索引 2。
把第一格的索引改成 2 会消除教学所需的错误，应判为不满足原目标。
其他异常类型即使也会“报错”，仍不符合此目标。观察预期错误后应继续后续步骤。

## 来源与改编

[原始讲义](https://github.com/swcarpentry/python-novice-inflammation/blob/a765c2c50b91d7618f803e12c23eef6607db2390/episodes/09-errors.md)第 34–70 行明确说明这是有意的错误，并提供函数与 traceback。
本包第一格函数文本与原文一致，第二格为 LessonProof 添加的理解检查。
原始 traceback 的行号和 Notebook 提示符随运行环境变化，只锁定错误类型及有意义的消息片段。
派生自 Copyright (c) [The Carpentries](https://carpentries.org/) 的教学材料。讲义与翻译按 CC BY 4.0，示例代码按 MIT；许可原文见 [LICENSE.md](LICENSE.md)。改编：中文节选、步骤编号、Notebook 分格及用于验收的 JSON 输出。

## 评测使用

学生只接收 `learner_files` 中的文件。原目标、预期结果和本说明留在评测侧。
检查器显示“可进入试跑”只说明材料准备好；本阶段不会自动判定 AI 是否保留了教学意图。
