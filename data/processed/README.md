# 处理结果

本目录用于保存通过 [config.py](../../config.py) v1.1规则验证的正式X/y交接文件。业务解释见 [PROJECT_CONTEXT.md](../../docs/PROJECT_CONTEXT.md)，完整会议决议见 [DECISIONS.md](../../docs/DECISIONS.md)。

目前尚无已验证的正式交接文件。`STEP1 OUTPUT/` 的清洗与EDA可作只读参考，但其 `features_A_only.csv`、`label_final.csv` 的标签、切分与字段边界不符合v1.1，不直接复制为正式接口。

后续从原始六表生成标签、切分和允许特征，按appid对齐，同时记录设计版本、切点、字段清单及各split计数；快照敏感性字段另存接口。先写入独立 `outputs/<阶段>/<UTC时间戳>/`，通过验证后形成交接文件，不覆盖原始输入或STEP1交付。数据文件不进入Git。
