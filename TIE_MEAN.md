# 最低分同分组的平均 AP

现有录入、修订和验收接口见 README.md。带材质检班需要在同一个固定任务上签发最低分同分组的平均 AP，夜班凭新报告号领取。原 `issue_report` 和 `read_report` 继续提供按 V1 固定顺序计算的 AP 和诊断。

## 计算口径

- 按 V1 读取固定任务的清册、人工标注修订、供应商预测修订和 IoU 门槛。分数按精确有理值比较，`1/3` 与 `2/6` 同分。
- 最低分组由**全批**最小分数上的全部预测组成。较高分预测按 V1 的分数降序、预测 ID 升序处理，包括较高分之间的并列。最低分组内按预测身份对全部全局顺序等权平均，同图同框的不同预测 ID 仍各占一位。
- 各顺序从确定的高分段继续，保留该段的全局秩、累计命中和逐图真值占用。仍按 V1 在同图未占用真值中选择达到闭门槛的最大 IoU，IoU 并列取最小真值 ID。每种顺序独立承接同一高分状态。
- 匹配职责交接的证据须足以在同一顺序内核算命中及其此前命中数。报告对各顺序按 V1 非插值 AP 计账，每个命中位置计入含本次命中的累计命中数除以实际全批秩，再以固定任务的全批真值总数归一。误报也占全局秩。精确均值为 `Fraction`，空预测为 `Fraction(0)`。原行重排且各行内容不变时，均值不变。
- 新入口覆盖至多 32 张清册图片，含无标注或无预测的图片。每图至多 4 个**最低分组**预测，较高分预测沿用 V1 的输入边界。两项上限均包含端点，超限拒发并报 `ValueError`。

## 签发与领取

从 `ledger` 提供 `issue_tie_mean(db, task_id) -> int` 和 `read_tie_mean(db, report_id)`。签发返回正整数报告号。读取返回结果对象，属性为 `report_id`、`task_id`、`metric` 和 `ap`。`metric` 的值为 `tie_mean_ap`，`ap` 是精确 `Fraction`。未知任务号或本口径报告号按 V1 的 ID 规则报 `KeyError`。

任务号、口径和均值在一次签发事务中保存。使用空闲连接发起写入。写入或提交失败传播原异常并回滚，可凭原任务重试。追加标注或预测修订以及关闭重开后，读取仍直接返回已签发值。保留 V1 入口、旧库中的原报告及完整原回归。新报告的存储和内部证据表示由实现决定。

## 两图三框样例

`tests/test_tie_mean_fixture.py` 提供三框数据和 V1 核账。两张图均为 4×4，`a` 有 A 和 B 两条标注，`z` 为空图。门槛为 `1/2`。F 可选 A 或 B 且优先 A，N 只能选 A，Z 在空图上失配。

| 最低分顺序 | 非插值 AP |
| --- | ---: |
| F、N、Z | 1/2 |
| F、Z、N | 1/2 |
| N、F、Z | 1 |
| N、Z、F | 5/6 |
| Z、F、N | 1/4 |
| Z、N、F | 7/12 |

新口径的均值为 `11/18`。同一组三框按原预测 ID 的 V1 报告为 `1/2`。若在 `a` 图另有同框于 A、分数为 `1` 的高分预测，且最低分组只有 F、N，均值为 `11/12`。若从原三框样例出发给 `z` 加一条与 Z 同框的真值 C，均值为 `22/27`。

满额样例可使用 `a` 和另外 31 张空图，均为 4×4。保留 A、B、F、N，在 `a` 加两个框为 `(3, 0, 4, 1)` 的误报，每张空图放四个同框误报。所有误报 ID 各不相同，128 个预测同分。预期均值为 `sum(Fraction(1, r) for r in range(1, 129)) / 128`。

新入口实现后的样例调用：

```python
from contextlib import closing
from fractions import Fraction

from ledger import (
    Image, freeze_task, issue_tie_mean, open_ledger, put_images,
    read_tie_mean, save_predictions, save_truth,
)
from tests.test_tie_mean_fixture import PREDICTION_ROWS, THRESHOLD, TRUTH_ROWS

with closing(open_ledger('inspection.sqlite3')) as db:
    catalog = put_images(db, 'tie-sample', [Image('a', 4, 4), Image('z', 4, 4)])
    truth = save_truth(db, catalog, TRUTH_ROWS)
    submitted = save_predictions(db, catalog, 'vendor', PREDICTION_ROWS)
    task = freeze_task(db, truth, submitted, THRESHOLD)
    report_id = issue_tie_mean(db, task)
    reordered = save_predictions(db, catalog, 'vendor', reversed(PREDICTION_ROWS))
    other_task = freeze_task(db, truth, reordered, THRESHOLD)
    other = read_tie_mean(db, issue_tie_mean(db, other_task))
    assert other.ap == Fraction(11, 18)
    save_truth(db, catalog, [('a', 'A', (3, 0, 4, 1))])

with closing(open_ledger('inspection.sqlite3')) as db:
    report = read_tie_mean(db, report_id)
    assert (report.report_id, report.task_id) == (report_id, task)
    assert report.metric == 'tie_mean_ap' and report.ap == Fraction(11, 18)
    print(report.task_id, report.metric, report.ap)
```

## 核验与演示

项目根目录以 Python 3.11 运行现有 `.pointwise-runtime.json`。现有清单为版本 1 的 CLI 类型，`setup` 为空，`verify` 和 `demo` 分别调用 `python3 -B verify.py` 与 `python3 -B demo.py`。交付时接通原回归和新增业务核验，核验失败返回非零退出码。演示三框重排得到相同均值，以及追加更正后重开领取固定报告。简述匹配证据保留的关联，以及报告使用实际全局秩时如何维持该关联。
