# 本地运行结果

当前命令为 `python -m src.data_audit_reproduce`，按 [config.py](../config.py) 的v1.1配置运行。原始六表和STEP1交付只读，每次结果保存到独立UTC时间戳目录：

```text
outputs/data_audit/<UTC时间戳>/steam_data_audit.json
```

审计结果须记录配置版本、六表哈希与结构检查、标签/切分计数，以及当前alpha=10、prior=0.10、多实体厂商历史规则的实际指标和历史窗口。2026-10-09当前实现已复算并与独立计算一致，2018滚动规则ROC-AUC 0.707903、AP 0.336896、期望Lift@10% 4.348139；历史窗口包含2017。不能把会议历史指标或旧alpha=20结果填成新结果。

既有alpha=20、历史总体正类率回退的JSON仅作历史证据；报告中明确其方法和版本。新运行不覆盖有效结果，重复或过时结果只按用户已授权范围清理。运行输出不进入Git、不随本次标准文档同步上传。结果解释与限制见 [PROJECT_CONTEXT.md](../docs/PROJECT_CONTEXT.md)。
