# 衡川带材视觉验收台账

标注员登记采图工位提供的图片尺寸和人工真值，验证员录入供应商预测并冻结两份明确修订。质检员签发整批 AP 和错检明细，用图 ID 和预测 ID 反馈复测。夜班可以重开台账，按白班报告号领取原结果。

## 运行

在项目根目录使用 Python 3.11。项目使用 Python 标准库和本地 SQLite。

```sh
python3 -B verify.py
python3 -B demo.py
```

`verify.py` 发现并运行 `tests/` 的全部回归。`demo.py` 读取 `samples/two_images.json`，在独立临时库内登记清册、保存修订、冻结、签发和重开领取。样例的首位预测属于空图，第二位预测命中唯一真值。手算 AP 为 1/2，报告给出空图的误报原行，两图均无漏检。检查失败时命令返回非零退出码。

## 公开 API

```python
from contextlib import closing
from fractions import Fraction
from ledger import (
    Image, freeze_task, issue_report, open_ledger, put_images,
    read_report, save_predictions, save_truth,
)

with closing(open_ledger('inspection.sqlite3')) as db:
    catalog_id = put_images(db, 'strip-017', [Image('a', 4, 4), Image('z', 4, 4)])
    truth_id = save_truth(db, catalog_id, [('a', 'T', (0, 0, 2, 2))])
    prediction_id = save_predictions(db, catalog_id, 'supplier', [
        ('hit', 'a', (0, 0, 2, 2), '1/3'),
        ('alarm', 'z', (0, 0, 1, 1), '2/3'),
    ])
    task_id = freeze_task(db, truth_id, prediction_id, Fraction(1, 2))
    report_id = issue_report(db, task_id)

with closing(open_ledger('inspection.sqlite3')) as db:
    report = read_report(db, report_id)
    print(report.task_id, report.ap, report.diagnostics)
```

- `open_ledger(path)` 打开连接、启用外键并按依赖顺序初始化表。`initialize(db)` 可在空闲连接上再次调用，保留已登记数据。调用方关闭连接。公开写入调用各自拥有一个事务，约定在连接无待提交事务时调用。
- `put_images(db, batch_name, images)` 接收非空 `Image(image_id, width, height)` 序列并返回清册号。批次名、提交名和各业务身份为非空文本，图尺寸是正整数像素。同名批次可有独立清册。图 ID 仅在所属清册内唯一。
- `save_truth(db, catalog_id, rows)` 接收 `(image_id, truth_id, rectangle)` 行并返回标注修订号。允许零行，真值 ID 在修订内的同一图唯一。更正保存为新修订。
- `save_predictions(db, catalog_id, submission_name, rows)` 接收 `(prediction_id, image_id, rectangle, score)` 行，保存原行顺序并返回预测修订号。零行和空真值图上的预测合法，预测 ID 在整份修订内唯一。同名提交可追加新修订。
- 矩形代表连续像素坐标 `(x0, y0, x1, y1)`。框须有正面积且完全位于引用图内，贴边合法。坐标、分数和门槛支持整数、Fraction、有限 Decimal、有限浮点数和 Fraction 接受的有理数字符串。浮点数按已有的二进制值精确转换。输入十进制意图时可传字符串。分数按精确数值排序。
- `freeze_task(db, truth_revision_id, prediction_revision_id, threshold)` 返回任务号。两个修订须来自同一清册，整批真值数为正，且 `0 < threshold <= 1`。任务保存明确的两种修订及门槛。
- `issue_report(db, task_id)` 返回报告号。`read_report(db, report_id)` 返回 `ReportSnapshot`，包含 `report_id`、`task_id`、`ap` 和 `diagnostics`。`diagnostics.image_misses` 包含清册每图的漏检身份，`diagnostics.false_positives` 包含原预测的秩、图、身份和原因。夜班领取直接读取已发布数据。

未知清册、修订、任务或报告号报 `KeyError`。无效清册、行、框、分数、门槛或任务组合报 `ValueError`，相关记录整次拒绝。SQLite 写入或提交失败会传播异常并回滚此次写入。

## 计算口径

所有预测共用一个从 1 起的秩，按分数降序、预测 ID 升序排位。每个预测在同图未占用的真值中选择 IoU 最大且达到闭门槛的框，IoU 并列时取最小真值 ID。矩形只在边界相接时交集为零。失配原因分别是 `no_truth`（同图无真值）、`below_threshold`（同图真值均低于门槛）和 `occupied`（合格真值均已被占用）。

非插值 AP 只在命中位置计入累计命中数与实际全局秩之比，再用固定任务的全批真值总数归一。空预测的 AP 为零。AP 和诊断消费同一轨迹。逐图漏检按图 ID、真值 ID 排序，误报按全局秩排序。清册、两类修订和任务保持固定，报告及其明细在同一事务中提交。
