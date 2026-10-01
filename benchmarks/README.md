# 公开课程基准 · 阅读与检查指南

这里有三套来自公开课程的教学片段，用于核对 LessonProof 后续的试跑和诊断能力。
三套课程已用于本地工作台的隔离执行与 AI 审阅开发验证。材料检查、执行结果、AI 结论和教师试用分别留存证据；人工记录表待实际试用填写。

## 从这里开始

在项目根目录运行，检查器使用 Python 3.10+ 标准库：

```powershell
python check_course.py benchmarks/numpy-data
python check_course.py benchmarks/expected-index-error
python check_course.py benchmarks/pandas-error-version
```

每次检查会在项目的 `work/checks/` 下生成独立目录，包含中文 `report.md` 和机器可读 `report.json`。
退出码 `0` 表示材料可进入试跑，`1` 表示材料需修正，`2` 表示报告保存失败。
报告中的 `material_status` 为 `ready` 或 `blocked`，`execution_status` 固定为 `not_run`。
这里声明的是课程目标环境；材料检查器不会安装 NumPy/pandas，也不会启动 Notebook 或联网抓取来源。实际试跑请通过工作台或 `verify_workflow.py`，见[验收操作指南](../docs/ACCEPTANCE.md)。

## 三节课分别看什么

| 课程 | 学生任务 | 可能卡住的位置 | 验收重点 |
| --- | --- | --- | --- |
| [数组数据读取与统计](numpy-data/lesson.md) | 读取 60 × 40 的 CSV 数组，观察索引并计算统计值 | 工作目录、表头误判、行列索引、输出格式 | 形状、取值、极值和均值均符合标准 |
| [读懂列表越界](expected-index-error/lesson.md) | 观察故意的 IndexError，解释最后一个有效索引 | 把教学错误当成需要修复的问题；报错后不知道要继续 | 保留预期异常，继续完成理解检查 |
| [缺失值与整数转换](pandas-error-version/lesson.md) | 尝试转换带缺失值的体重列，定位缺失记录 | 讲义中的异常名称和现代 pandas 不一致 | 修正讲义说明，同时保留教学所需的转换失败 |

建议先只读各课程的 `lesson.md`，按学生视角标出不清楚的步骤，再读对应 `reference.md` 核对设计目的。
历史案例取自已经修复的 [Data Carpentry #571](https://github.com/datacarpentry/python-ecology-lesson/pull/571/files)，原始两版节选保存在该课程目录中。
数组数据是上游课程的虚构教学数据；体重数据取自 [Portal Project Teaching Database](https://doi.org/10.6084/m9.figshare.1314459) 的公开教学快照。

## 课程包约定

每套使用 `course.json` 登记标题、来源类型、环境、步骤输入、学生材料和文件 SHA-256：

- `lesson.md` 使用 `## 步骤 <id>` 标题，顺序与 Notebook 代码格及验收标准一致；代码围栏中的示例标题不算实际步骤。
- `lesson.ipynb` 是 nbformat 4.5，cell ID 唯一；待试跑代码格的执行编号为 `null`，输出为 `[]`。清理旧输出应在工作副本完成。
- `acceptance.json` 沿用现有执行验收格式；`reference.md` 保存问题目标、出处和改编依据。
- `learner_files` 明确列出学生接收的文件。后续试跑只传这些文件；验收标准、历史修订后的节选和参考说明留在评测侧。
- `steps[].inputs` 声明该步骤使用的包内文件。静态检查验证清单中的引用，不推断代码里的动态路径或自然语言含义；这些要由后续逐步试跑核对。
- `files` 记录本地文件的 SHA-256。`sources` 记录完整原始文件的固定提交、下载地址、SHA-256、对应本地文件和改编说明。两类校验值用途不同。

路径使用 `/` 分隔且限定在包内；绝对路径、向上跳转、Windows 设备名/数据流和指向包外的链接会被拦截。单文件检查上限为 8 MiB。
检查器读取登记的课程材料，不执行代码或改动输入。`ready` 只表示符合本阶段的材料格式，不是课程正确性或代码安全性的结论。

## 验收标准如何固定

本地检查会核对登记的文件版本，并将清单和验收标准的 SHA-256 写入报告。修改任何登记材料后，旧登记会使检查失败。
教师开始一次试跑前应保存这份报告和课程副本；修订时保留相同的验收目标，并由评测侧用原报告核对。
校验值用于比较版本；工作台会将审核绑定具体材料版本，修订后须重新试跑，验收标准保持原值。本地文件不属于外部防篡改存储；重新登记清单本身不能视为教师批准修改验收目标。

历史案例中，代码按预期报错可以通过执行验收，但讲义仍可能有错。`reference.md` 单独定义需要发现的讲义问题，之后还要核对修订是否解决它。

## 人工试用记录

[manual_trials.csv](manual_trials.csv) 是空白记录表。每行表示一个参与者完成一个案例的一次尝试，尚未填入实测数据。

| 字段 | 填写方式 |
| --- | --- |
| trial_id / participant_id / case_id | 唯一试次、匿名参与者编号、课程目录名 |
| condition | manual、general_ai 或 lessonproof，分别表示人工、普通 AI 辅助和本项目 |
| course_manifest_sha256 / acceptance_sha256 | 从本次检查报告复制，锁定参与者收到的版本和验收目标 |
| started_at / finished_at | 带时区的 ISO 8601 时间，例如 2026-09-06T10:00:00+08:00 |
| active_seconds / review_seconds | 有效操作与人工复核时间；操作时间包含查资料和修改，不含休息与被动等待 |
| findings / confirmed_findings / missed_findings | 发现的问题、复核确认的问题、按原目标核对后的漏报；多项使用分号分隔 |
| repair_result | not_needed、passed、failed 或 not_attempted；由复核人员填写 |
| model_cost_cny | 实际模型调用费用；人工条件填 0，费用不可得时留空 |
| evidence_path / notes | 原始记录、修改对比或报告的位置；备注可记录中断、求助及顺序影响 |

有休息或等待时另外记入备注；整单耗时由起止时间计算，与有效操作时间分别统计。
本批公开课程用于开发和练习。正式对照实验应使用独立课程，平衡难度与体验顺序，避免先读参考答案再计时造成偏差。

## 来源与许可

派生教学材料 Copyright (c) [The Carpentries](https://carpentries.org/)，文字按 CC BY 4.0，示例代码按 MIT；各课程保留上游 `LICENSE.md`。
中文翻译、路径整理、Notebook 分格与验收输出均在各自来源记录中说明。Portal 教学数据库数据按 CC0 提供，子集保留选行规则与原始文件校验值。
三套样本提供可复核的开发依据。人工节省时间、AI 命中率和实际课堂收益在采集试用数据后计算。
